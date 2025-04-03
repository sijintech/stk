import abc
import numpy as np


class Shape(abc.ABC):

    def __init__(self):
        # 中心位置
        self.position = None
        # 半尺寸
        self.half_size = None

    @abc.abstractmethod
    def get_type(self):
        pass

    @abc.abstractmethod
    def set_half_size(self):
        pass

    @abc.abstractmethod
    def collide_with(self):
        pass

    @abc.abstractmethod
    @staticmethod
    def random_generate(self, position, method=None):
        pass

    def check_box_collision(self, other: 'Shape') -> bool:
        return np.all(np.abs(self.position - other.position) <= self.half_size + other.half_size)


class Cylinder(Shape):
    '''
    实心圆柱体
    '''

    def __init__(self, position, radius, height, orientation, voxel_template=None):
        super().__init__()
        self.position = np.array(position, dtype=np.float32)
        self.radius = radius
        self.height = height
        self.orientation = np.array(orientation / np.linalg.norm(orientation))
        self.voxel_template = voxel_template if radius > 0.5 else None
        self.cutoff = max(2 * radius + 1, height + 1) if radius > 0.5 else 1
        self.half_size = self.set_half_size()

    def set_half_size(self):
        half_size = self.radius * np.sqrt(1 - self.orientation**2) + (self.height / 2) * np.abs(self.orientation)
        return half_size

    @staticmethod
    def random_generate(self, space, position, cylinder_message, method="parallel", voxel_template=None):
        if method == 'parallel':
            orientation = [0, 0, 1]
        else:
            # -45° ~ 45°
            phi = np.random.uniform(0, 360) * np.pi / 180
            theta = np.random.uniform(-45, 45) * np.pi / 180
            x = np.sin(theta) * np.cos(phi)
            y = np.sin(theta) * np.sin(phi)
            z = np.cos(theta)
            orientation = np.array([x, y, z])

        new_cylinder = Cylinder(position, cylinder_message['radius'], cylinder_message['height'], orientation, voxel_template)
        return new_cylinder if new_cylinder.is_within_bounds(space) else None

    # TODO
    # 边界检查也有问题，后续需要修改
    # 现在主要是比较圆柱的两端圆心是否在空间内进行判断
    # 正确的方法应该是比较边界，而不是两端圆心
    def is_within_bounds(self, space):
        half_height = self.height / 2
        end1 = self.position - half_height * self.orientation
        end2 = self.position + half_height * self.orientation
        for p in [end1, end2]:
            if not (0 <= p[0] < space.nx and 0 <= p[1] < space.ny and 0 <= p[2] < space.nz):
                return False

        return True

    @staticmethod
    def get_volumn(self, cyliner_message):
        return np.pi * cyliner_message['radius']**2 * height if cyliner_message['radius'] > 0.5 else 1

    def collide_with(self, other, space=None):
        if not self.check_box_collision(other):
            return False
        return other.collide_with_cylinder(self)

    def collide_with_cylinder(self, other: 'Cylinder'):
        # 计算底部圆心
        pos1 = self.position - (self.height / 2) * self.orientation
        pos2 = other.position - (other.height / 2) * self.orientation

        # 轴线向量
        d = self.orientation
        e = other.orientation
        p = pos1 - pos2

        # 向量点积
        d_d = np.dot(d, d)
        e_e = np.dot(e, e)
        d_e = np.dot(d, e)
        p_d = np.dot(p, d)
        p_e = np.dot(p, e)

        # 计算 t 和 s
        denom = d_d * e_e - d_e * d_e
        if abs(denom) < 1e-6:
            t = p_d / d_d if d_d > 1e-6 else 0
            s = 0
        else:
            t = (p_d * e_e - p_e * d_e) / denom
            s = (p_d * d_e - p_e * d_d) / denom

        # 裁剪 t 和 s
        t = max(0, min(self.height, t))
        s = max(0, min(other.height, s))

        # 计算最近点
        closest1 = pos1 + t * self.orientation
        closest2 = pos2 + s * other.orientation

        # 计算距离
        dist = np.linalg.norm(closest1 - closest2)

        # 判断是否相交
        return dist < (self.radius + other.radius)

    def collide_with_sphere(self, other: 'Sphere'):
        # 计算球心到圆柱质心的距离
        cm = other.position - self.position
        print("cm", cm)
        # 沿圆柱轴线的投影长度
        t0 = np.dot(cm, self.orientation)
        # print("t0", t0)
        # 计算球心到圆柱轴线的距离
        d = np.linalg.norm(np.cross(cm, self.orientation))
        # print("distance", d)
        # 计算径向和轴向距离项
        radial_term = max(d - self.radius, 0.00)
        axial_term = max(abs(t0) - self.height / 2.0, 0.0)
        # print("radial_term", radial_term)
        # print("axial_term", axial_term)

        # 判断相交条件
        return (radial_term**2 + axial_term**2) <= other.radius**2

    def collide_with_sphere_shell(self, other: 'SphereShell'):
        raise NotImplementedError("collide_with_sphere_shell not implemented")

    def get_type(self):
        return "cylinder"


class Sphere(Shape):
    '''
    实心球体
    '''

    def __init__(self, position, radius, voxel_template=None):
        super().__init__()
        self.position = position
        self.radius = radius
        self.voxel_template = voxel_template
        self.half_size = self.set_half_size()

    def set_half_size(self):
        return np.array([self.radius, self.radius, self.radius])

    @staticmethod
    def random_generate(self, space, position, sphere_message, method=None, voxel_template=None):
        new_sphere = Sphere(position, sphere_message['radius'], voxel_template)
        return new_sphere if new_sphere.is_within_bounds(space) else None

    def is_within_bounds(self, space):
        end1 = self.position - self.radius
        end2 = self.position + self.radius
        for p in [end1, end2]:
            if not (0 <= p[0] < space.nx and 0 <= p[1] < space.ny and 0 <= p[2] < space.nz):
                return False

        return True

    @staticmethod
    def get_volumn(self, sphere_message):
        return (4 / 3) * np.pi * sphere_message['radius']**3 if radius > 0.5 else 1

    def collide_with(self, other):
        if not self.check_box_collision(other):
            return False
        return other.collide_with_sphere(self)

    def collide_with_sphere(self, other: 'Sphere'):
        distance = np.linalg.norm(self.position, other.position)
        return distance < (self.radius + other.radius)

    def collide_with_cylinder(self, other: 'Cylinder'):
        return other.collide_with_sphere(self)

    def get_type(self):
        return "sphere"


class SphereShell(Shape):
    '''
    空心球体
    '''

    def __init__(self, position, radius, shell_thickness):
        super().__init__()
        self.position = position
        self.radius = radius
        self.shell_thickness = shell_thickness
        self.box = self.set_half_size()

    def set_half_size(self):
        pass

    def get_type(self):
        return "sphere_shell"


if __name__ == '__main__':
    position = [0, 0, 0]
    radius = 1
    height = 1
    orientation = [0, 1, 0]
    cylinder = Cylinder(position, radius, height, orientation)

    position1 = [0, 2, 0]
    radius1 = 1
    sphere = Sphere(position1, radius1)

    print(cylinder.collide_with(sphere))

shape_map = {
    'cylinder': Cylinder,
    'sphere': Sphere,
}
