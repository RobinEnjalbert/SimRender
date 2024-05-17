from typing import Optional, List
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from threading import Thread
from multiprocessing.shared_memory import SharedMemory
from time import sleep
from numpy import array, ndarray, isnan
from vedo import Plotter, Mesh, Points, Arrows
from matplotlib.colors import Normalize
from matplotlib.pyplot import get_cmap

from SimRender.generic.remote.memory import Memory
from SimRender.generic.utils import fix_memory_leak, get_mesh_cells


class Factory:

    def __init__(self, socket_port: int, plotter: Plotter):
        """
        This class is used to manage the communication with the simulation process.
        It loads the visualization data from shared arrays.

        :param socket_port: Port number of the simulation socket.
        :param plotter: Plotter instance.
        """

        # CPython issue: https://github.com/python/cpython/issues/82300
        fix_memory_leak()

        # Connect to the simulation process
        self.__socket = socket(AF_INET, SOCK_STREAM)
        self.__socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.__socket.connect(('localhost', socket_port))

        # Load the shared numpy array for synchronization with format [do_exit, do_synchronize, step_counter]
        sync_array = array([0, 0, 0], dtype=int)
        sm_name = self.__socket.recv(int.from_bytes(bytes=self.__socket.recv(2), byteorder='big')).decode('utf-8')
        self.__sync_sm = SharedMemory(create=False, name=sm_name)
        self.__sync_arr = ndarray(shape=sync_array.shape, dtype=sync_array.dtype, buffer=self.__sync_sm.buf)

        # Create the visual objects and the associated memories containers
        self.__objects: List[Object] = []
        self.__memories: List[Memory] = []

        # Receive the number of visual objects, then information about each visual object shared array
        nb_object = int.from_bytes(bytes=self.__socket.recv(2), byteorder='big')
        for _ in range(nb_object):

            # Receive the object type
            object_type = self.__socket.recv(int.from_bytes(bytes=self.__socket.recv(2),
                                                            byteorder='big')).decode(encoding='utf-8')

            # Receive data shared arrays in memory
            memory = Memory(remote=self.__socket)

            # Create the visual object
            self.__objects.append(Object(object_type=object_type, memory=memory))

        # Plotter instance
        self.plt = plotter

    @property
    def vedo_objects(self) -> List[Points]:
        """
        Get the list of visual objects in the factory.
        """
        return [o.object for o in self.__objects]

    @property
    def count(self) -> int:
        """
        Get the counter value in the simulation process.
        """

        return self.__sync_arr[2]

    def listen(self) -> None:
        """
        Launch the listening thread of the factory.
        """

        # Launch the listening thread
        thread = Thread(target=self.__listen)
        thread.start()

        # Notify to the simulation process that the viewer is ready
        self.__socket.send(b'done')

    def __listen(self) -> None:
        """
        Listening thread of the factory.
        """

        # Do nothing while the do_exit flag is not turned on
        while not self.__sync_arr[0]:
            # Do not access the shared array value to often
            sleep(0.1)

        # Do not exit while the rendering window is not closed
        while not self.plt._must_close_now:
            pass
        self.close()

    def update(self) -> None:
        """
        Update the visual objects.
        """

        # Update each visual object
        for o in self.__objects:
            o.update(plt=self.plt)

        # Notify the simulation process if the do_synchronize flag is turned on
        if self.__sync_arr[1] == 1:
            self.__socket.send(b'done')

    def close(self):
        """
        Close the communication with the simulation process.
        """

        # Close the connection with the shared memories (synchronization array and each visual object array)
        self.__sync_sm.close()
        for memory in self.__memories:
            memory.close()

        # Notify the simulation
        self.__socket.send(b'done')

        # Wait for the simulation process to close connections with the shared memories
        self.__socket.recv(4)

        # Close socket
        self.__socket.close()


class Object:

    def __init__(self, object_type: str, memory: Memory):
        """
        This class gathers the methods to create and update visual object instances.

        :param object_type: Object type (mesh, points...).
        :param memory: Shared memories access.
        """

        # Shared memories access
        self.__memory = memory

        # Create the visual object instance
        self.object: Optional[Points] = None
        self.__getattribute__(f'_create_{object_type}')()

        # Define the update method depending on the visual object type
        self.update = self.__getattribute__(f'_update_{object_type}')

    def _create_mesh(self) -> None:
        """
        Create a mesh instance.
        """

        # Access data fields
        data = self.__memory.data
        cells = data['cells'] if len(data['cells'].shape) > 1 else get_mesh_cells(flat_cells=data['cells'])

        # Create instance
        color = data['color'].item() if len(data['color'].shape) == 0 else data['color']
        self.object = Mesh(inputobj=[data['positions'], cells], c=color, alpha=data['alpha'].item())
        self.object.wireframe(value=data['wireframe'].item()).lw(linewidth=data['line_width'].item())

        # Apply cmap
        if not isnan(data['colormap_field']).any():
            if not isnan(data['colormap_range']).any():
                self.object.cmap(input_cmap=data['colormap'].item(), input_array=data['colormap_field'],
                                 vmin=data['colormap_range'][0], vmax=data['colormap_range'][1])
            else:
                self.object.cmap(input_cmap=data['colormap'].item(), input_array=data['colormap_field'])

        # Apply texture
        elif not isnan(data['texture_coords']).any() and data['texture_name'].item() != '':
            self.object.texture(tname=data['texture_name'].item(), tcoords=data['texture_coords'])

    def _update_mesh(self, plt: Plotter) -> None:
        """
        Update a mesh instance.
        """

        self.object: Mesh

        # Update positions
        positions, dirty = self.__memory.get_data(field_name='positions')
        if dirty:
            self.object.vertices = positions

        # Update color
        color, dirty = self.__memory.get_data(field_name='color')
        color = color.item() if len(color.shape) == 0 else color
        if dirty:
            self.object.color(color)
        alpha, dirty = self.__memory.get_data(field_name='alpha')
        if dirty:
            self.object.alpha(alpha.item())
        colormap_field, dirty = self.__memory.get_data(field_name='colormap_field')
        if dirty:
            colormap, _ = self.__memory.get_data(field_name='colormap')
            colormap_range, _ = self.__memory.get_data(field_name='colormap_range')
            if not isnan(colormap_range).any():
                self.object.cmap(input_cmap=colormap.item(), input_array=colormap_field,
                                 vmin=colormap_range[0], vmax=colormap_range[1])
            else:
                self.object.cmap(input_cmap=colormap.item(), input_array=colormap_field)

        # Update rendering style
        wireframe, dirty = self.__memory.get_data(field_name='wireframe')
        if dirty:
            self.object.wireframe(wireframe.item())
        line_width, dirty = self.__memory.get_data(field_name='line_width')
        if dirty:
            self.object.lw(linewidth=line_width.item())

    def _create_points(self) -> None:
        """
        Create a point cloud instance.
        """

        # Access data fields
        data = self.__memory.data

        # Create instance
        color = data['color'].item() if len(data['color'].shape) == 0 else data['color']
        self.object = Points(inputobj=data['positions'], r=data['point_size'].item(),
                             c=color, alpha=data['alpha'].item())

        # Apply cmap
        if not isnan(data['colormap_field']).any():
            if not isnan(data['colormap_range']).any():
                self.object.cmap(input_cmap=data['colormap'].item(), input_array=data['colormap_field'],
                                 vmin=data['colormap_range'][0], vmax=data['colormap_range'][1])
            else:
                self.object.cmap(input_cmap=data['colormap'].item(), input_array=data['colormap_field'])

    def _update_points(self, plt: Plotter):
        """
        Update a point cloud instance.
        """

        self.object: Points

        # Update positions
        positions, dirty = self.__memory.get_data(field_name='positions')
        if dirty:
            self.object.vertices = positions

        # Update color
        color, dirty = self.__memory.get_data(field_name='color')
        color = color.item() if len(color.shape) == 0 else color
        if dirty:
            self.object.color(color)
        alpha, dirty = self.__memory.get_data(field_name='alpha')
        if dirty:
            self.object.alpha(alpha.item())
        colormap_field, dirty = self.__memory.get_data(field_name='colormap_field')
        if dirty:
            colormap, _ = self.__memory.get_data(field_name='colormap')
            colormap_range, _ = self.__memory.get_data(field_name='colormap_range')
            if not isnan(colormap_range).any():
                self.object.cmap(input_cmap=colormap.item(), input_array=colormap_field,
                                 vmin=colormap_range[0], vmax=colormap_range[1])
            else:
                self.object.cmap(input_cmap=colormap.item(), input_array=colormap_field)

        # Update rendering style
        point_size, dirty = self.__memory.get_data(field_name='point_size')
        if dirty:
            self.object.point_size(point_size.item())

    def _create_arrows(self) -> None:
        """
        Create an arrows instance.
        """

        # Access data fields
        data = self.__memory.data

        # Create instance
        color = data['color'].item() if len(data['color'].shape) == 0 else data['color']
        self.object = Arrows(start_pts=data['positions'], end_pts=data['positions'] + data['vectors'],
                             c=color, alpha=data['alpha'].item())

        # Apply cmap
        if not isnan(data['colormap_field']).any():
            if not isnan(data['colormap_range']).any():
                cmap_norm = Normalize(vmin=float(data['colormap_range'][0]), vmax=float(data['colormap_range'][1]))
            else:
                cmap_norm = Normalize(vmin=min(data['colormap_field']), vmax=max(data['colormap_field']))
            cmap = get_cmap(data['colormap'].item())
            self.object.color(c=cmap(cmap_norm(data['colormap_field']))[:, :3])

    def _update_arrows(self, plt: Plotter):
        """
        Update an arrows instance.
        """

        self.object: Arrows

        # Update positions & vectors
        positions, dirty_p = self.__memory.get_data(field_name='positions')
        vectors, dirty_v = self.__memory.get_data(field_name='vectors')
        if dirty_p or dirty_v:
            plt.remove(self.object)
            self._create_arrows()
            plt.add(self.object)

        # Update color
        color, dirty = self.__memory.get_data(field_name='color')
        color = color.item() if len(color.shape) == 0 else color
        if dirty:
            self.object.color(color)
        alpha, dirty = self.__memory.get_data(field_name='alpha')
        if dirty:
            self.object.alpha(alpha.item())
        colormap_field, dirty = self.__memory.get_data(field_name='colormap_field')
        if dirty:

            if not isnan(self.__memory.data['colormap_range']).any():
                cmap_norm = Normalize(vmin=float(self.__memory.data['colormap_range'][0]),
                                      vmax=float(self.__memory.data['colormap_range'][1]))
            else:
                cmap_norm = Normalize(vmin=min(colormap_field), vmax=max(colormap_field))
            cmap = get_cmap(self.__memory.data['colormap'].item())
            self.object.color(c=cmap(cmap_norm(colormap_field))[:, :3])
