#include "nmathbasic/nmathbasic.h"



void n_data_2D_double_init(int x, int y, double (**outptr)[x][y])
{
    *outptr = calloc(x*y,sizeof(double));
}

void n_data_2D_double_fill(int x, int y, double array[x][y])
{
    int count = 0;
    size_t i = 0;
    size_t j = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            array[i][j] = count;
            count++;
        }
    }
}

void n_data_2D_double_assign(int x, int y, double array[x][y], double value)
{
    // int count = 0;
    size_t i = 0;
    size_t j = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            array[i][j] = value;
        }
    }
}


void n_data_2D_double_print(int x, int y, double array[x][y])
{
    size_t i = 0;
    size_t j = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            ZF_LOGI("i:%zu j:%zu val:%f", i, j, array[i][j]);
        }
    }
}