#include "niobasic/datFile.h"



void n_datFile_3D_double_read_f(int *x, int *y, int *z, double **data, const char *file){
    n_datFile_3D_double_read(*x, *y, *z, NPTR2ARR3D(double,*data,*x, *y, *z),file);
}
void n_datFile_3D_double_read(int x, int y, int z, double data[x][y][z], const char *file)
{
    n_datFile_4D_double_read(x, y, z, 1, NPTR2ARR4D(double, NARR2PTR(double,data),x, y, z, 1), file);
}

void n_datFile_3D_double_write_f(int *x, int *y, int *z, double **data, const char *file){
    n_datFile_3D_double_write(*x, *y, *z, NPTR2ARR3D(double,*data,*x, *y, *z),file);
}
void n_datFile_3D_double_write(int x, int y, int z, double data[x][y][z], const char *file){
    n_datFile_4D_double_write(x,y,z,1,NPTR2ARR4D(double, NARR2PTR(double,data),x, y, z, 1),file);
}