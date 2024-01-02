#include "nmathfft/nmathfft.h"


void n_data_3D_complex_init(int x, int y, int z, fftw_complex (**outptr)[x][y][z])
{
    *outptr = calloc(x*y*z,sizeof(fftw_complex));
}

void n_data_3D_complex_fill(int x, int y, int z, fftw_complex array[x][y][z])
{
    size_t i=0;
    size_t j=0;
    size_t k=0;
    int count = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                array[i][j][k] = count;
                count++;
            }
        }
    }
}

void n_data_3D_complex_print(int x, int y, int z, fftw_complex array[x][y][z])
{
    size_t i=0;
    size_t j=0;
    size_t k=0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                ZF_LOGI("i:%zu j:%zu k:%zu val:%f %f", i, j, k, creal(array[i][j][k]), cimag(array[i][j][k]));
            }
        }
    }
}