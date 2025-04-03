import abc
import numpy as np


class Space(abc.ABC):

    @abc.abstractmethod
    def get_space_dimension(self):
        pass

    @abc.abstractmethod
    def get_volume(self):
        pass

    @abc.abstractmethod
    def generate_halton_points(self, n_points):
        pass

    @abc.abstractmethod
    def random_point(self):
        pass


class ThreeDimensionSpace(Space):

    def __init__(self, nx, ny, nz):
        super().__init__()
        self.nx = nx
        self.ny = ny
        self.nz = nz

    def get_space_dimension(self):
        return 3

    def get_volume(self):
        return self.nx * self.ny * self.nz

    def generate_halton_points(self, n_points, bases=[2, 3, 5]):
        x = halton_sequence(n_points, bases[0]) * self.nx
        y = halton_sequence(n_points, bases[1]) * self.ny
        z = halton_sequence(n_points, bases[2]) * self.nz
        points = np.vstack((x, y, z)).T
        return points.astype(int)

    def random_point(self):
        # 随机生成一个点
        return np.random.uniform([0, 0, 0], [self.nx, self.ny, self.nz], (1, 3)).astype(int)


class FourDimensionSpace(Space):

    def __init__(self, nx, ny, nz, nt):
        super().__init__()
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.nt = nt

    def get_space_dimension(self):
        return 4


class FiveDimensionSpace(Space):

    def __init__(self, nx, ny, nz, nt, nu):
        super().__init__()
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.nt = nt
        self.nu = nu

    def get_space_dimension(self):
        return 5


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
