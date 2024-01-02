#include "nmathbasic/nmathbasic.h"


void n_data_4D_double_init(int x, int y, int z, int c, double (**outptr)[x][y][z][c])
{
    *outptr = calloc(x*y*z*c,sizeof(double));
}

void n_data_4D_double_fill(int x, int y, int z, int c, double array[x][y][z][c])
{
    int count = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                for (l = 0; l < c; l++)
                {
                    array[i][j][k][l] = count;
                    count++;
                }
            }
        }
    }
}

void n_data_4D_double_assign(int x, int y, int z, int c, double array[x][y][z][c], double value[c])
{
    // int count = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                for (l = 0; l < c; l++)
                {
                    array[i][j][k][l] = value[c];
                }
            }
        }
    }
}

void n_data_4D_double_print(int x, int y, int z, int c, double array[x][y][z][c])
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                for (l = 0; l < c; l++)
                {
                    ZF_LOGI("l: %zu, i:%zu j:%zu k:%zu val:%f", l, i, j, k, array[l][i][j][k]);
                }
            }
        }
    }
}