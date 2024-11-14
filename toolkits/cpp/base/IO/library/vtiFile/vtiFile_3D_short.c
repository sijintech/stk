#include "niobasic/vtiFile.h"

void n_vtiFile_3D_short_write_f(int *x, int *y, int *z, short **data, const char *fileName)
{
    n_vtiFile_4D_short_write(*x, *y, *z, 1, NPTR2ARR4D(short, *data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_short_write(int x, int y, int z, short data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_short_write(x, y, z, 1, NPTR2ARR4D(short, NARR2PTR(short,data),x, y, z, 1), fileName);
}



void n_vtiFile_3D_short_read_f(int *x, int *y, int *z, short **data, const char *fileName)
{
    n_vtiFile_4D_short_read(*x, *y, *z, 1, NPTR2ARR4D(short, *data,*x, *y, *z, 1), fileName);
}

void n_vtiFile_3D_short_read(int x, int y, int z, short data[x][y][z], const char *fileName)
{
    n_vtiFile_4D_short_read(x, y, z, 1, NPTR2ARR4D(short, NARR2PTR(short,data),x, y, z, 1), fileName);
}
