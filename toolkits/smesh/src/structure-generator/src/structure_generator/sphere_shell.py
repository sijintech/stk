import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import time
from abc import ABC, abstractmethod


# Halton 序列生成函数
def halton_sequence(size, base):
    seq = []
    for i in range(1, size + 1):
        num = 0.0
        f = 1.0 / base
        n = i
        while n > 0:
            digit = n % base
            num += digit * f
            f /= base
            n //= base
        seq.append(num)
    return np.array(seq)


# 三维 Halton 序列生成
def generate_halton_points(n_points, bounds_x, bounds_y, bounds_z):
    bases = [2, 3, 5]
    x = halton_sequence(n_points, bases[0]) * (bounds_x[1] - bounds_x[0]) + bounds_x[0]
    y = halton_sequence(n_points, bases[1]) * (bounds_y[1] - bounds_y[0]) + bounds_y[0]
    z = halton_sequence(n_points, bases[2]) * (bounds_z[1] - bounds_z[0]) + bounds_z[0]
    points = np.vstack((x, y, z)).T
    return points.astype(int)


# 预计算实心球体素模板
def precompute_sphere_voxel(radius, buffer_size):
    buffer_size = max(int(2 * radius + 1), 3)
    center = buffer_size / 2
    voxel = np.zeros((buffer_size, buffer_size, buffer_size), dtype=np.int8)  # 用 int8 与壳统一
    x, y, z = np.ogrid[0:buffer_size, 0:buffer_size, 0:buffer_size]
    dist = np.sqrt((x - center) ** 2 + (y - center) ** 2 + (z - center) ** 2)
    voxel[dist <= radius] = 1  # 球内部标记为 1
    return voxel


# 预计算球壳体素模板
def precompute_sphere_shell_voxel(radius, thickness, buffer_size):
    buffer_size = max(int(2 * (radius + thickness) + 1), 3)
    center = buffer_size / 2
    voxel = np.zeros((buffer_size, buffer_size, buffer_size), dtype=np.int8)
    x, y, z = np.ogrid[0:buffer_size, 0:buffer_size, 0:buffer_size]
    dist = np.sqrt((x - center) ** 2 + (y - center) ** 2 + (z - center) ** 2)
    voxel[dist <= radius] = 1  # 球内部为 1
    voxel[(dist > radius) & (dist <= radius + thickness)] = 2  # 壳为 2
    return voxel


# 抽象基类：插入相
class Structure(ABC):
    def __init__(self, position, grid_shape):
        self.position = np.array(position, dtype=int)
        self.grid_shape = grid_shape
        self.box = self._get_bounding_box()

    @abstractmethod
    def _get_bounding_box(self):
        pass

    def check_overlap(self, other):
        box1, box2 = self.box, other.box
        return not (box1[3] < box2[0] or box1[0] > box2[3] or
                    box1[4] < box2[1] or box1[1] > box2[4] or
                    box1[5] < box2[2] or box1[2] > box2[5])


# 实心球类
class Sphere(Structure):
    def __init__(self, position, radius, grid_shape, voxel_template=None):
        self.radius = radius
        self.thickness = 0  # 无壳
        self.cutoff = 2 * radius + 1 if radius > 0.5 else 1
        self.voxel_template = voxel_template if radius > 0.5 else None
        super().__init__(position, grid_shape)

    def _get_bounding_box(self):
        if self.radius > 0.5:
            return np.array([
                self.position[0] - self.radius, self.position[1] - self.radius, self.position[2] - self.radius,
                self.position[0] + self.radius, self.position[1] + self.radius, self.position[2] + self.radius
            ])
        else:
            return np.array([
                self.position[0], self.position[1], self.position[2],
                self.position[0] + 1, self.position[1] + 1, self.position[2] + 1
            ])

    def apply_voxel(self, grid):
        if self.radius > 0.5 and self.voxel_template is not None:
            half = self.voxel_template.shape[0] / 2
            x0, y0, z0 = self.position - half
            x1, y1, z1 = self.position + half
            sx0, sy0, sz0 = max(0, int(np.ceil(x0))), max(0, int(np.ceil(y0))), max(0, int(np.ceil(z0)))
            sx1, sy1, sz1 = min(self.grid_shape[0], int(np.ceil(x1))), min(self.grid_shape[1], int(np.ceil(y1))), min(
                self.grid_shape[2], int(np.ceil(z1)))
            tx0, ty0, tz0 = sx0 - x0, sy0 - y0, sz0 - z0
            tx1, ty1, tz1 = tx0 + (sx1 - sx0), ty0 + (sy1 - sy0), tz0 + (sz1 - sz0)
            grid_slice = grid[sx0:sx1, sy0:sy1, sz0:sz1]
            template_slice = self.voxel_template[int(tx0):int(tx1), int(ty0):int(ty1), int(tz0):int(tz1)]
            if grid_slice.shape == template_slice.shape:
                mask = (grid_slice == 0)
                grid[sx0:sx1, sy0:sy1, sz0:sz1][mask] = template_slice[mask]
        else:
            x, y, z = self.position
            if 0 <= x < self.grid_shape[0] and 0 <= y < self.grid_shape[1] and 0 <= z < self.grid_shape[2]:
                grid[x, y, z] = 1


# 球壳类
class SphereShell(Structure):
    def __init__(self, position, radius, thickness, grid_shape, voxel_template=None):
        self.radius = radius
        self.thickness = thickness
        self.cutoff = 2 * (radius + thickness) + 1 if radius > 0.5 else 1
        self.voxel_template = voxel_template if radius > 0.5 else None
        super().__init__(position, grid_shape)

    def _get_bounding_box(self):
        if self.radius > 0.5:
            outer_radius = self.radius + self.thickness
            return np.array([
                self.position[0] - outer_radius, self.position[1] - outer_radius, self.position[2] - outer_radius,
                self.position[0] + outer_radius, self.position[1] + outer_radius, self.position[2] + outer_radius
            ])
        else:
            return np.array([
                self.position[0], self.position[1], self.position[2],
                self.position[0] + 1, self.position[1] + 1, self.position[2] + 1
            ])

    def apply_voxel(self, grid):
        if self.radius > 0.5 and self.voxel_template is not None:
            half = self.voxel_template.shape[0] / 2
            x0, y0, z0 = self.position - half
            x1, y1, z1 = self.position + half
            sx0, sy0, sz0 = max(0, int(np.ceil(x0))), max(0, int(np.ceil(y0))), max(0, int(np.ceil(z0)))
            sx1, sy1, sz1 = min(self.grid_shape[0], int(np.ceil(x1))), min(self.grid_shape[1], int(np.ceil(y1))), min(
                self.grid_shape[2], int(np.ceil(z1)))
            tx0, ty0, tz0 = sx0 - x0, sy0 - y0, sz0 - z0
            tx1, ty1, tz1 = tx0 + (sx1 - sx0), ty0 + (sy1 - sy0), tz0 + (sz1 - sz0)
            grid_slice = grid[sx0:sx1, sy0:sy1, sz0:sz1]
            template_slice = self.voxel_template[int(tx0):int(tx1), int(ty0):int(ty1), int(tz0):int(tz1)]
            if grid_slice.shape == template_slice.shape:
                mask = (grid_slice == 0)
                grid[sx0:sx1, sy0:sy1, sz0:sz1][mask] = template_slice[mask]
        else:
            x, y, z = self.position
            if 0 <= x < self.grid_shape[0] and 0 <= y < self.grid_shape[1] and 0 <= z < self.grid_shape[2]:
                grid[x, y, z] = 1


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


# 生成球面可视化数据
def generate_sphere_surface(center, radius, num_points=20):
    u = np.linspace(0, 2 * np.pi, num_points)
    v = np.linspace(0, np.pi, num_points)
    x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radius * np.outer(np.ones(np.size(u)), np.cos(v))
    return x, y, z


# 主程序：插入结构（支持实心球和球壳）
def insert_structures(volume_fraction, radius, grid_x, grid_y, grid_z, structure_type="sphere", thickness=0, max_iterations=10000):
    start_time = time.time()
    grid_shape = (grid_x, grid_y, grid_z)

    # 根据结构类型选择模板和外径
    outer_radius = radius + thickness if structure_type == "sphere_shell" else radius
    if radius > 0.5:
        if structure_type == "sphere":
            voxel_template = precompute_sphere_voxel(radius, int(2 * radius + 1))
        elif structure_type == "sphere_shell":
            voxel_template = precompute_sphere_shell_voxel(radius, thickness, int(2 * (radius + thickness) + 1))
        else:
            raise ValueError("structure_type must be 'sphere' or 'sphere_shell'")
    else:
        voxel_template = None

    spatial_grid = SpatialGrid(grid_shape, 2 * outer_radius + 1 if radius > 0.5 else 1)
    structures = []
    iteration = 0

    # 计算目标结构数量
    total_volume = grid_x * grid_y * grid_z
    if structure_type == "sphere":
        structure_volume = (4 / 3) * np.pi * radius ** 3 if radius > 0.5 else 1
    else:  # sphere_shell
        sphere_volume = (4 / 3) * np.pi * radius ** 3
        shell_volume = (4 / 3) * np.pi * ((radius + thickness) ** 3 - radius ** 3)
        structure_volume = sphere_volume + shell_volume if radius > 0.5 else 1
    target_num_structures = int(volume_fraction * total_volume / structure_volume)

    while len(structures) < target_num_structures and iteration < max_iterations:
        iteration += 1
        new_structures = []
        attempts = target_num_structures - len(structures)

        if iteration == 1:
            bounds_x = (outer_radius, grid_x - outer_radius)
            bounds_y = (outer_radius, grid_y - outer_radius)
            bounds_z = (outer_radius, grid_z - outer_radius)
            positions = generate_halton_points(attempts, bounds_x, bounds_y, bounds_z)
        else:
            positions = np.random.uniform([outer_radius] * 3,
                                          [grid_x - outer_radius, grid_y - outer_radius, grid_z - outer_radius],
                                          (attempts, 3)).astype(int)

        for pos in positions:
            if structure_type == "sphere":
                struct = Sphere(pos, radius, grid_shape, voxel_template)
            else:  # sphere_shell
                struct = SphereShell(pos, radius, thickness, grid_shape, voxel_template)
            nearby = spatial_grid.get_nearby_structures(struct)
            overlap = False
            for neighbor in nearby:
                if struct.check_overlap(neighbor):
                    overlap = True
                    break
            if not overlap:
                new_structures.append(struct)
                spatial_grid.add_structure(struct)

        structures.extend(new_structures)
        print(f"Iteration {iteration}, Structures: {len(structures)}, Time: {time.time() - start_time:.2f}s")

    iteration_time = time.time() - start_time
    final_num_structures = len(structures)

    # 生成体素网格
    voxel_grid = np.zeros(grid_shape, dtype=np.int8)  # 0: 空, 1: 球, 2: 壳
    for struct in structures:
        struct.apply_voxel(voxel_grid)

    # 分离球和壳的体素点
    sphere_points = np.where(voxel_grid == 1)
    shell_points = np.where(voxel_grid == 2)
    sphere_x, sphere_y, sphere_z = sphere_points
    shell_x, shell_y, shell_z = shell_points

    # 可视化1：球面和壳面
    fig1 = plt.figure(figsize=(10, 10))
    ax1 = fig1.add_subplot(111, projection='3d')
    for struct in structures:
        x, y, z = generate_sphere_surface(struct.position, struct.radius)
        ax1.plot_surface(x, y, z, color='b', alpha=0.5, label='Sphere' if struct.thickness == 0 else None)
        if struct.thickness > 0:  # 仅对球壳绘制外层
            x, y, z = generate_sphere_surface(struct.position, struct.radius + struct.thickness)
            ax1.plot_surface(x, y, z, color='r', alpha=0.3, label='Shell')
    ax1.set_xlim(0, grid_x)
    ax1.set_ylim(0, grid_y)
    ax1.set_zlim(0, grid_z)
    ax1.set_box_aspect([grid_x, grid_y, grid_z])
    plt.title(f"Final (Surface): {final_num_structures}/{target_num_structures} Structures, Time: {iteration_time:.2f}s")

    # 可视化2：体素点
    fig2 = plt.figure(figsize=(10, 10))
    ax2 = fig2.add_subplot(111, projection='3d')
    ax2.scatter(sphere_x, sphere_y, sphere_z, c='b', s=5, alpha=0.5, label='Sphere')
    if structure_type == "sphere_shell":
        ax2.scatter(shell_x, shell_y, shell_z, c='r', s=5, alpha=0.1, label='Shell')
    ax2.set_xlim(0, grid_x)
    ax2.set_ylim(0, grid_y)
    ax2.set_zlim(0, grid_z)
    ax2.set_box_aspect([grid_x, grid_y, grid_z])
    ax2.legend()
    plt.title(f"Final (Voxel Points): {final_num_structures}/{target_num_structures} Structures, Time: {iteration_time:.2f}s")

    plt.show()

    print("\nGenerated Structure Information:")
    print(f"  Grid Size: {grid_x} x {grid_y} x {grid_z}")
    print(f"  Structure Type: {structure_type}")
    print(f"  Sphere Radius: {radius}")
    print(f"  Shell Thickness: {thickness}")
    print(f"  Target Volume Fraction: {volume_fraction:.2%}")
    print(f"  Target Number of Structures: {target_num_structures}")
    print(f"  Final Number of Structures Inserted: {final_num_structures}")

    return structures, voxel_grid


# 示例运行
if __name__ == "__main__":
    # 示例1：实心球
    print("Running Sphere Example:")
    grid_x, grid_y, grid_z = 100, 100, 100
    volume_fraction = 0.02
    radius = 5
    structures_sphere, grid_sphere = insert_structures(volume_fraction, radius, grid_x, grid_y, grid_z, structure_type="sphere")

    # 示例2：球壳
    print("\nRunning SphereShell Example:")
    grid_x, grid_y, grid_z = 100, 100, 100
    volume_fraction = 0.05
    radius = 3.0
    thickness = 1.0
    structures_shell, grid_shell = insert_structures(volume_fraction, radius, grid_x, grid_y, grid_z, structure_type="sphere_shell", thickness=thickness)