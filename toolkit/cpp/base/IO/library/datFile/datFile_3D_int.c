#include "niobasic/datFile.h"


void n_datFile_3D_int_read_f(int *x, int *y, int *z, int **data, const char *file)
{
    n_datFile_3D_int_read(*x, *y, *z, NPTR2ARR3D(int,*data,*x,*y,*z), file);
}
void n_datFile_3D_int_read(int x, int y, int z, int data[x][y][z], const char *file)
{
    n_datFile_4D_int_read(x, y, z, 1, NPTR2ARR4D(int, NARR2PTR(int,data),x, y, z, 1), file);
}

void n_datFile_3D_int_write_f(int *x, int *y, int *z, int **data, const char *file){
    n_datFile_3D_int_write(*x,*y,*z,NPTR2ARR3D(int,*data,*x,*y,*z),file);
}
void n_datFile_3D_int_write(int x, int y, int z, int data[x][y][z], const char *file){
    n_datFile_4D_int_write(x,y,z,1,NPTR2ARR4D(int, NARR2PTR(int,data),x, y, z, 1),file);
}

