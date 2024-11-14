#include "niobasic/vtiFile.h"


void n_vtiFile_3D_double_write_f(int *x, int *y, int *z,  double **data, const char *fileName)
{
    n_vtiFile_4D_double_write(*x, *y, *z, 1, NPTR2ARR4D(double, *data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_double_write(int x, int y, int z, double data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_double_write(x, y, z, 1, NPTR2ARR4D(double, NARR2PTR(double,data),x, y, z, 1), fileName);
}


void n_vtiFile_3D_double_read_f(int *x, int *y, int *z, double **data, const char *fileName)
{
    n_vtiFile_4D_double_read(*x, *y, *z, 1, NPTR2ARR4D(double, *data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_double_read(int x, int y, int z, double data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_double_read(x, y, z, 1, NPTR2ARR4D(double, NARR2PTR(double,data),x, y, z, 1), fileName);
}


