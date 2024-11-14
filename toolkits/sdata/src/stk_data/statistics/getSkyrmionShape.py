import numpy as np
import argparse


class SkyrmionShape:

    def __init__(self, nx=210, ny=210, nz=17, nk=12, nR=100, dx=2.0, dy=2.0, save_file_name='GetSkyrmionShape120.dat') -> None:
        # initialize parameters
        self.nx, self.ny, self.nz, self.nk = nx, ny, nz, nk - 1
        self.nR = nR
        self.dx, self.dy = dx, dy
        self.pi = np.arccos(-1.0)

        # initialize arrays
        self.p = np.zeros((nz, ny, nx, 3))
        self.wall = np.zeros((2, 2))
        self.radius = np.zeros(2)
        self.center = np.zeros(2)
        self.width = np.zeros((2, 2))
        self.width_avg = np.zeros(2)
        self.posit = np.zeros(2)
        self.valu = np.zeros(2)
        self.pGrad = np.zeros((ny, nx, 3, 2))
        self.chargeDensity = np.zeros((ny, nx))
        self.charge = 0.0
        self.save_file_name = save_file_name

    def read_input(self, filename):
        # read the magnetic data from file
        with open(filename, 'r') as f:
            self.first_line = f.readline()  # Read and skip the first line,
            read_nx, read_ny, read_nz = map(int, self.first_line.split())
            if read_nx != self.nx or read_ny != self.ny or read_nz != self.nz:
                raise KeyError("nx, ny, nz are inconsistent with the file reading.")

            # read p array from file
            for _ in range(self.nx * self.ny * self.nz):
                i, j, k, p1, p2, p3 = map(float, f.readline().split())
                i, j, k = int(i), int(j), int(k)
                self.p[k - 1, j - 1, i - 1, 0] = p1
                self.p[k - 1, j - 1, i - 1, 1] = p2
                self.p[k - 1, j - 1, i - 1, 2] = p3

    def calculate_walls_and_widths(self):
        # reset posit and valu arrays
        self.posit.fill(0)
        self.valu.fill(0)

        # calculate the first half for width(1, 1)
        for i in range(0, self.nx // 2 - 1):
            if self.p[self.nk, self.ny // 2 - 1, i, 2] * self.p[self.nk, self.ny // 2 - 1, i + 1, 2] < 0:
                self.wall[0, 0] = (i + 1) + self.p[self.nk, self.ny // 2 - 1, i, 2] / (self.p[self.nk, self.ny // 2 - 1, i, 2] - self.p[self.nk, self.ny // 2 - 1, i + 1, 2])
            if self.p[self.nk, self.ny // 2 - 1, i, 2] > 0.3 and self.p[self.nk, self.ny // 2 - 1, i + 1, 2] < 0.3:
                self.posit[0] = i + 1
                self.valu[0] = self.p[self.nk, self.ny // 2 - 1, i, 2]
            elif self.p[self.nk, self.ny // 2 - 1, i, 2] > -0.3 and self.p[self.nk, self.ny // 2 - 1, i + 1, 2] < -0.3:
                self.posit[1] = i + 2
                self.valu[1] = self.p[self.nk, self.ny // 2 - 1, i + 1, 2]
        self.width[0, 0] = -2. * (self.posit[1] - self.posit[0]) / (self.valu[1] - self.valu[0])

        # calculate the second half for width(1, 2)
        self.posit.fill(0)
        self.valu.fill(0)
        for i in range(self.nx // 2, self.nx - 1):
            if self.p[self.nk, self.ny // 2 - 1, i, 2] * self.p[self.nk, self.ny // 2 - 1, i + 1, 2] < 0:
                self.wall[0, 1] = (i + 1) + self.p[self.nk, self.ny // 2 - 1, i, 2] / (self.p[self.nk, self.ny // 2 - 1, i, 2] - self.p[self.nk, self.ny // 2 - 1, i + 1, 2])
            if self.p[self.nk, self.ny // 2 - 1, i, 2] < -0.3 and self.p[self.nk, self.ny // 2 - 1, i + 1, 2] > -0.3:
                self.posit[0] = i + 1
                self.valu[0] = self.p[self.nk, self.ny // 2 - 1, i, 2]
            elif self.p[self.nk, self.ny // 2 - 1, i, 2] < 0.3 and self.p[self.nk, self.ny // 2 - 1, i + 1, 2] > 0.3:
                self.posit[1] = i + 2
                self.valu[1] = self.p[self.nk, self.ny // 2 - 1, i + 1, 2]
        self.width[0, 1] = 2 * (self.posit[1] - self.posit[0]) / (self.valu[1] - self.valu[0])

        # similarly calculate width(2, 1) and width(2, 2) for the y-dimension
        self.posit.fill(0)
        self.valu.fill(0)
        for i in range(0, self.ny // 2 - 1):
            if self.p[self.nk, i, self.nx // 2 - 1, 2] * self.p[self.nk, i + 1, self.nx // 2 - 1, 2] < 0:
                self.wall[1, 0] = (i + 1) + self.p[self.nk, i, self.nx // 2 - 1, 2] / (self.p[self.nk, i, self.nx // 2 - 1, 2] - self.p[self.nk, i + 1, self.nx // 2 - 1, 2])
            if self.p[self.nk, i, self.nx // 2 - 1, 2] > 0.3 and self.p[self.nk, i + 1, self.nx // 2 - 1, 2] < 0.3:
                self.posit[0] = i + 1
                self.valu[0] = self.p[self.nk, i, self.nx // 2 - 1, 2]
            elif self.p[self.nk, i, self.nx // 2 - 1, 2] > -0.3 and self.p[self.nk, i + 1, self.nx // 2 - 1, 2] < -0.3:
                self.posit[1] = i + 2
                self.valu[1] = self.p[self.nk, i + 1, self.nx // 2 - 1, 2]
        self.width[1, 0] = -2 * (self.posit[1] - self.posit[0]) / (self.valu[1] - self.valu[0])

        # final part of y-dimension
        self.posit.fill(0)
        self.valu.fill(0)
        for i in range(self.ny // 2, self.ny - 1):
            if self.p[self.nk, i, self.nx // 2 - 1, 2] * self.p[self.nk, i + 1, self.nx // 2 - 1, 2] < 0:
                self.wall[1, 1] = (i + 1) + self.p[self.nk, i, self.nx // 2 - 1, 2] / (self.p[self.nk, i, self.nx // 2 - 1, 2] - self.p[self.nk, i + 1, self.nx // 2 - 1, 2])
            if self.p[self.nk, i, self.nx // 2 - 1, 2] < -0.3 and self.p[self.nk, i + 1, self.nx // 2 - 1, 2] > -0.3:
                self.posit[0] = i + 1
                self.valu[0] = self.p[self.nk, i, self.nx // 2 - 1, 2]
            elif self.p[self.nk, i, self.nx // 2 - 1, 2] < 0.3 and self.p[self.nk, i + 1, self.nx // 2 - 1, 2] > 0.3:
                self.posit[1] = i + 2
                self.valu[1] = self.p[self.nk, i + 1, self.nx // 2 - 1, 2]

        self.width[1, 1] = 2. * (self.posit[1] - self.posit[0]) / (self.valu[1] - self.valu[0])

        self.radius[0] = (self.wall[0, 1] - self.wall[0, 0]) / 2.
        self.radius[1] = (self.wall[1, 1] - self.wall[1, 0]) / 2.

        self.center[0] = (self.wall[0, 1] + self.wall[0, 0]) / 2.
        self.center[1] = (self.wall[1, 1] + self.wall[1, 0]) / 2.

        self.width_avg[0] = (self.width[0, 0] + self.width[0, 1]) / 2.
        self.width_avg[1] = (self.width[1, 0] + self.width[1, 1]) / 2.

        for i in range(1, self.nx - 1):
            for j in range(1, self.ny - 1):
                if ((i + 1) - (self.nx + 1) // 2)**2 + ((j + 1) - (self.nx + 1) // 2)**2 <= (self.nR - 2.)**2:
                    self.pGrad[j, i, :, 0] = 1. / 2 * (self.p[self.nk, j, i + 1, :] - self.p[self.nk, j, i - 1, :]) / self.dx
                    self.pGrad[j, i, :, 1] = 1. / 2 * (self.p[self.nk, j + 1, i, :] - self.p[self.nk, j - 1, i, :]) / self.dy

        self.chargeDensity = 0.25e0 / self.pi * \
                           ((self.p[self.nk, :, :, 0] * (self.pGrad[:, :, 1, 0] * self.pGrad[:, :, 2, 1] - self.pGrad[:, :, 2, 0] * self.pGrad[:, :, 1, 1])) + \
                            (self.p[self.nk, :, :, 1] * (self.pGrad[:, :, 2, 0] * self.pGrad[:, :, 0, 1] - self.pGrad[:, :, 0, 0] * self.pGrad[:, :, 2, 1])) + \
                            (self.p[self.nk, :, :, 2] * (self.pGrad[:, :, 0, 0] * self.pGrad[:, :, 1, 1] - self.pGrad[:, :, 1, 0] * self.pGrad[:, :, 0, 1])))

        self.charge = np.sum(self.chargeDensity) * self.dx * self.dy

        # check position of centers and walls to make sure the postprocessing is correct
        # centers should be around nx/2, ny/2; walls should be inside the island
        # output the results
        titles = ["radius", "center", "wall_1", "wall_2", "width_1", "width_2", "width_avg"]
        first_line = [self.radius[0], self.center[0], self.wall[0, 0], self.wall[0, 1], self.width[0, 0], self.width[0, 1], self.width_avg[0]]
        second_line = [self.radius[1], self.center[1], self.wall[1, 0], self.wall[1, 1], self.width[1, 0], self.width[1, 1], self.width_avg[1]]

        centered_titles = [text.center(12) for text in titles]
        center_first_line = [f"{value:.2f}".center(12) for value in first_line]
        center_second_line = [f"{value:.2f}".center(12) for value in second_line]
        print(' '.join(centered_titles))
        print(' '.join(center_first_line))
        print(' '.join(center_second_line))
        print("Topological charge".rjust(12))
        print("{:12.4f}".format(self.charge))

        # save the results
        if self.save_file_name != None:
            with open(self.save_file_name, 'w') as f:
                f.write(' '.join(centered_titles) + '\n')
                f.write(' '.join(center_first_line) + '\n')
                f.write(' '.join(center_second_line) + '\n')
                f.write("Topological charge\n".rjust(12))
                f.write("{:12.4f}\n".format(self.charge))


def get_skyrmion_shape(nx, ny, nz, nk, nR, dx, dy, load_file_name="magnt.in", save_file_name="GetSkyrmionShape120.dat"):
    shape_obj = SkyrmionShape(nx, ny, nz, nk, nR, dx, dy, save_file_name)
    shape_obj.read_input(load_file_name)
    shape_obj.calculate_walls_and_widths()


if __name__ == '__main__':
    #============ use example ============
    # python pythonfile.py --nx 250 --ny 250 --nk 6 --nR 100 --dx 2.0 --dy 2.0 --load_file_name magnt.in --save_file_name GetSkyrmionShape120.dat
    # python pythonfile.py --nx 250 --ny 250 --nk 6
    # python pythonfile.py --load_file_name magnt.in
    #=====================================

    parser = argparse.ArgumentParser()
    parser.add_argument("--nx", type=int, default=250)
    parser.add_argument("--ny", type=int, default=250)
    parser.add_argument("--nz", type=int, default=10)
    parser.add_argument("--nk", type=int, default=6)
    parser.add_argument("--nR", type=int, default=100)
    parser.add_argument("--dx", type=float, default=2.0)
    parser.add_argument("--dy", type=float, default=2.0)
    parser.add_argument("--load_file_name", type=str, default="magnt.in")
    parser.add_argument("--save_file_name", type=str, default="GetSkyrmionShape120.dat")
    args = parser.parse_args()

    shape_obj = SkyrmionShape(nx=args.nx, ny=args.ny, nz=args.nz, nk=args.nk, nR=args.nR, dx=args.dx, dy=args.dy, save_file_name=args.save_file_name)
    shape_obj.read_input(args.load_file_name)
    shape_obj.calculate_walls_and_widths()
