from typing import Dict, List, Tuple
from socket import socket
from multiprocessing.shared_memory import SharedMemory
from numpy import array, ndarray, frombuffer, dtype as np_dtype


class Memory:

    def __init__(self, remote: socket, store_data: bool):
        """
        This class loads the shared arrays from the simulation process for each data field of a visual object.

        :param remote: Remote socket to communicate with.
        """

        # Create the shared memories container
        self.__buffers: Dict[str, List[SharedMemory]] = {}

        # Create the shared array containers for data and dirty flags
        self.__data: Dict[str, ndarray] = {}
        self.__dirty: Dict[str, ndarray] = {}

        # Receive the number of data fields, then information about each field shared array
        nb_data_fields = int.from_bytes(bytes=remote.recv(2), byteorder='big')
        for _ in range(nb_data_fields):

            # Receive the shared memory name and the data field name
            sm_name = remote.recv(int.from_bytes(bytes=remote.recv(2), byteorder='big')).decode('utf-8')
            field_name = remote.recv(int.from_bytes(bytes=remote.recv(2), byteorder='big')).decode('utf-8')

            # Receive the data shape and type
            shape = frombuffer(remote.recv(int.from_bytes(bytes=remote.recv(2),
                                                          byteorder='big'))).astype(int).reshape(-1)
            dtype = np_dtype(remote.recv(int.from_bytes(bytes=remote.recv(2), byteorder='big')).decode('utf-8'))

            # Dirty flag template
            dirty = array(False, dtype=bool)

            # Load the shared memories buffers for the data field and the associated dirty flag
            value_sm = SharedMemory(create=False, name=sm_name)
            dirty_sm = SharedMemory(create=False, name=f'{sm_name}_dirty')
            self.__buffers[field_name] = [value_sm, dirty_sm]

            # Load the shared arrays for the data field and the associated dirty flag
            self.__data[field_name] = ndarray(shape=shape, dtype=dtype, buffer=value_sm.buf)
            self.__dirty[field_name] = ndarray(shape=dirty.shape, dtype=dirty.dtype, buffer=dirty_sm.buf)

        if store_data:
            self.memory = {field_name: [] for field_name in self.__data.keys()}
        self.get = self.__get if not store_data else self.__get_and_store

    def __get(self) -> Tuple[Dict[str, ndarray], Dict[str, ndarray]]:
        return self.__data, self.__dirty

    def __get_and_store(self) -> Tuple[Dict[str, ndarray], Dict[str, ndarray]]:
        for field_name in self.memory.keys():
            self.memory[field_name].append(array(self.__data[field_name]))
        return self.__data, self.__dirty

    def get_frame(self, idx: int) -> Dict[str, ndarray]:

        return {field_name: self.memory[field_name][idx] for field_name in self.memory.keys()}

    def close(self) -> None:
        """
        Close every shared memories.
        """

        # Close each data/dirty shared memory pair
        for buffers in self.__buffers.values():
            buffers[0].close()
            buffers[1].close()
