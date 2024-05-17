from typing import Dict, Any
import Sofa

from SimRender.sofa.local.sofa_objects.base import Points


class PointCollisionModel(Points):

    def __init__(self, sofa_object: Sofa.Core.Object):

        super().__init__(sofa_object=sofa_object)

    def create(self) -> Dict[str, Any]:

        # Position
        self.positions = self.sofa_node.findLink('state').getLinkedBase().getData('position').value
        # Color & alpha
        self.alpha = 1.
        self.color = 'orange5'
        # Point size
        self.point_size = 7
        return super().create()

    def update(self) -> Dict[str, Any]:

        # Position
        self.positions = self.sofa_node.findLink('state').getLinkedBase().getData('position').value
        return super().update()
