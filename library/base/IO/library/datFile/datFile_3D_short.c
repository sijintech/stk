#include "niobasic/datFile.h"


void n_datFile_3D_short_read_f(int *x, int *y, int *z, short **data, const char *file)
{
    n_datFile_3D_short_read(*x, *y, *z, NPTR2ARR3D(short,*data,*x,*y,*z), file);
}
void n_datFile_3D_short_read(int x, int y, int z, short data[x][y][z], const char *file)
{
    n_datFile_4D_short_read(x, y, z, 1, NPTR2ARR4D(short, NARR2PTR(short,data),x,y,z,1), file);
}

void n_datFile_3D_short_write_f(int *x, int *y, int *z, short **data, const char *file){
    n_datFile_3D_short_write(*x,*y,*z,NPTR2ARR3D(short,*data,*x,*y,*z),file);
}
void n_datFile_3D_short_write(int x, int y, int z, short data[x][y][z], const char *file){
    n_datFile_4D_short_write(x,y,z,1,NPTR2ARR4D(short, NARR2PTR(short,data),x,y,z,1),file);
}

