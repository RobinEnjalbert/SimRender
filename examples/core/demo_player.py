from SimRender.core import Player
from simulation import Simulation


if __name__ == '__main__':

    # Create the simulation and the viewer
    simu = Simulation()
    player = Player()

    # Init the visualization
    simu.init_viewer(viewer=player)
    player.launch()

    # Run some steps of the simulation
    while player.is_open:
        simu.step()
        player.render()

    # Close the rendering window
    player.shutdown()
