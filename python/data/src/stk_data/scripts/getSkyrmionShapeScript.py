from ..statistics.getSkyrmionShape import SkyrmionShape
import argparse


def get_skyrmion_shape():
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
