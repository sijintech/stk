#include "nmathbasic/nmathbasic.h"

void n_data_3D_double_init(int x, int y, int z, double (**outptr)[x][y][z])
{
    *outptr = calloc(x * y * z, sizeof(double));
}

void n_data_3D_double_fill(int x, int y, int z, double array[x][y][z])
{
    int count = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
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

void n_data_3D_double_assign(int x, int y, int z, double array[x][y][z],
                             double value)
{
    // int count = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                array[i][j][k] = value;
            }
        }
    }
}

void n_data_3D_double_print(int x, int y, int z, double array[x][y][z])
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    for (i = 0; i < x; i++)
    {
        for (j = 0; j < y; j++)
        {
            for (k = 0; k < z; k++)
            {
                ZF_LOGI("i:%zu j:%zu k:%zu val:%f", i, j, k, array[i][j][k]);
            }
        }
    }
}

void n_data_3D_convert_double_to_short(int x, int y, int z,
                                       double array[x][y][z],
                                       short out[x][y][z], int n,
                                       double keys[n])
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
                out[i][j][k] = n;
                for (l = 0; l < n; l++)
                {
                    if (array[i][j][k] < keys[l])
                    {
                        out[i][j][k] = l;
                        // ZF_LOGI("convert %i %i %i %i", i, j, k, l);
                        break;
                    }
                }
            }
        }
    }
}