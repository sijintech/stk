#include "niobasic/vtiFile.h"

void n_vtiFile_3D_int_write_f(int *x, int *y, int *z, int **data, const char *fileName)
{
    n_vtiFile_4D_int_write(*x, *y, *z, 1, NPTR2ARR4D(int,*data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_int_write(int x, int y, int z, int data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_int_write(x, y, z, 1, NPTR2ARR4D(int, NARR2PTR(int,data),x, y, z, 1), fileName);
}



void n_vtiFile_3D_int_read_f(int *x, int *y, int *z, int **data, const char *fileName)
{
    n_vtiFile_4D_int_read(*x, *y, *z, 1, NPTR2ARR4D(int,*data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_int_read(int x, int y, int z, int data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_int_read(x, y, z, 1, NPTR2ARR4D(int, NARR2PTR(int,data),x, y, z, 1), fileName);
}
