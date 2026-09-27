# 空间网格优化
class SpatialGrid:

    def __init__(self, grid_shape, cell_size):
        self.grid_shape = grid_shape
        self.cell_size = cell_size
        self.cells = {}

    def get_cell(self, pos):
        return tuple((pos // self.cell_size).astype(int))

    def add_structure(self, struct):
        cell = self.get_cell(struct.position)
        if cell not in self.cells:
            self.cells[cell] = []
        self.cells[cell].append(struct)

    def get_nearby_structures(self, struct):
        cell = self.get_cell(struct.position)
        nearby = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for dz in [-1, 0, 1]:
                    neighbor_cell = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                    if neighbor_cell in self.cells:
                        nearby.extend(self.cells[neighbor_cell])
        return nearby
