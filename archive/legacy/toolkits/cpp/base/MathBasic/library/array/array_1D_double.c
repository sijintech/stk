#include "nmathbasic/nmathbasic.h"

void n_data_1D_double_assign(int x, double array[x], double value)
{
    // int count = 0;
    size_t i = 0;
    for (i = 0; i < x; i++)
    {
        array[i] = value;
    }
}

int double_compare_function(const void* a, const void* b)
{
    return ((int)(*(double*)a + 0.5) - (int)(*(double*)b + 0.5));
}

void n_data_1D_double_sort_ascend(int n, double in[n])
{
    qsort(in, n, sizeof(double), double_compare_function);
}

void n_data_1D_double_min_index_f(int* out, int* n, double** in)
{
    *out = n_data_1D_double_min_index(*n, *in);
}

int n_data_1D_double_min_index(int n, double in[n])
{
    double hold = in[0];
    int index = 0;
    int i = 0;
    for (i = 0; i < n; i++)
    {
        if (in[i] < hold)
        {
            hold = in[n];
            index = i;
        }
    }
    return index;
}

void n_data_1D_double_max_index_f(int* out, int* n, double** in)
{
    *out = n_data_1D_double_max_index(*n, *in);
}

int n_data_1D_double_max_index(int n, double in[n])
{
    double hold = in[0];
    int index = 0;
    int i = 0;
    for (i = 0; i < n; i++)
    {
        if (in[i] > hold)
        {
            hold = in[n];
            index = i;
        }
    }
    return index;
}

void n_data_1D_double_add(int n, double out[n], double add[n])
{
    size_t i = 0;
    for (i = 0; i < n; i++)
    {
        out[i] = out[i] + add[i];
    }
}

void n_data_1D_double_substract_const(int n, double out[n], double sub)
{
    size_t i = 0;
    for (i = 0; i < n; i++)
    {
        out[i] = out[i] - sub;
    }
}

void n_data_1D_double_multiply(int n, double out[n], double in[n])
{
    size_t i = 0;
    for (i = 0; i < n; i++)
    {
        out[i] = out[i] * in[i];
    }
}

void n_data_double_get_nth_component(int total, int rank, int nth,
                                     double out[total], double in[total][rank])
{
    size_t i = 0;
    for (i = 0; i < total; i++)
    {
        out[i] = in[i][nth];
    }
}

void n_data_double_set_nth_component(int total, int rank, int nth,
                                     double out[total][rank], double in[total])
{
    size_t i = 0;
    for (i = 0; i < total; i++)
    {
        out[i][nth] = in[i];
    }
}