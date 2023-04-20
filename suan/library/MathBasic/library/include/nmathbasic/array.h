

#ifndef __NMATHBASICARRAY_H__
#define __NMATHBASICARRAY_H__

#include <nmathbasic/errors.h>
#include <nmathbasic/exports.h>

#ifdef __cplusplus
extern "C"
{
#endif

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_1D_double_sort_ascend(int n, double in[n]);

    NMATHBASICPUBFUN int NMATHBASICCALL
    n_data_1D_double_min_index(int n, double in[n]);
    NMATHBASICPUBFUN int NMATHBASICCALL
    n_data_1D_double_max_index(int n, double in[n]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_1D_double_assign(int n,
                                                                 double in[n],
                                                                 double value);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_2D_double_init(int x, int y, double (**outptr)[x][y]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_2D_double_fill(int x, int y, double array[x][y]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_2D_double_print(int x, int y, double array[x][y]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_2D_double_assign(int x, int y, double array[x][y], double value);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_double_init(int x, int y, int z, double (**outptr)[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_double_fill(int x, int y, int z, double array[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_double_assign(
        int x, int y, int z, double array[x][y][z], double value);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_double_print(int x, int y, int z, double array[x][y][z]);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_int_assign(int x, int y, int z, int array[x][y][z], int value);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_int_init(int x, int y, int z, int (**outptr)[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_int_fill(int x, int y, int z,
                                                            int array[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_int_print(int x, int y, int z, int array[x][y][z]);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_int_equal_count(
        int x, int y, int z, int array[x][y][z], int value);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_int_not_equal_count(
        int x, int y, int z, int array[x][y][z], int value);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_int_exist_range(
        int out[6], int x, int y, int z, int array[x][y][z], int value);

    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_unsigned_int_assign(
        int x, int y, int z, unsigned int array[x][y][z], unsigned int value);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_unsigned_int_init(
        int x, int y, int z, unsigned int (**outptr)[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_unsigned_int_fill(
        int x, int y, int z, unsigned int array[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_unsigned_int_print(
        int x, int y, int z, unsigned int array[x][y][z]);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_unsigned_int_equal_count(
        int x, int y, int z, unsigned int array[x][y][z], unsigned int value);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_unsigned_int_not_equal_count(
        int x, int y, int z, unsigned int array[x][y][z], unsigned int value);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_unsigned_int_exist_range(
        int out[6], int x, int y, int z, unsigned int array[x][y][z],
        unsigned int value);

    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_convert_double_to_short(
        int x, int y, int z, double array[x][y][z], short out[x][y][z], int n,
        double keys[n]);

    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_short_assign(
        int x, int y, int z, short array[x][y][z], short value);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_short_init(int x, int y, int z, short (**outptr)[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_short_fill(int x, int y, int z, short array[x][y][z]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_3D_short_print(int x, int y, int z, short array[x][y][z]);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_short_equal_count(
        int x, int y, int z, short array[x][y][z], short value);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_3D_short_not_equal_count(
        int x, int y, int z, short array[x][y][z], short value);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_3D_short_exist_range(
        int out[6], int x, int y, int z, short array[x][y][z], short value);

    NMATHBASICPUBFUN void NMATHBASICCALL n_data_4D_double_init(
        int x, int y, int z, int c, double (**outptr)[x][y][z][c]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_4D_double_fill(int x, int y, int z, int c, double array[x][y][z][c]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_4D_double_assign(
        int x, int y, int z, int c, double array[x][y][z][c], double value[c]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_4D_double_print(
        int x, int y, int z, int c, double array[x][y][z][c]);

    NMATHBASICPUBFUN int NMATHBASICCALL n_data_1D_min_index(int n,
                                                            double in[n]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_1D_min_index_f(int* out, int* n,
                                                               double** in);
    NMATHBASICPUBFUN int NMATHBASICCALL n_data_1D_max_index(int n,
                                                            double in[n]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_data_1D_max_index_f(int* out, int* n,
                                                               double** in);

    NMATHBASICPUBFUN void NMATHBASICCALL n_data_1D_double_add(int n,
                                                              double out[n],
                                                              double add[n]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_1D_double_substract_const(int n, double out[n], double sub);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_1D_double_multiply(int n, double out[n], double in[n]);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_double_get_nth_component(int total, int rank, int nth,
                                    double out[total], double in[total][rank]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_data_double_set_nth_component(int total, int rank, int nth,
                                    double out[total][rank], double in[total]);

#define INIT_GET_MACRO(_3, _4, _5, NAME, ...) NAME

#define n_data_4D_init(x, y, z, c, data)                                       \
    _Generic((data),                     \
             double *                    \
             : n_data_4D_double_init,    \
               int *                     \
             : n_data_4D_int_init)(x, y, z, c, data)

#define n_data_3D_init(x, y, z, data)                                          \
    _Generic((data),                          \
             double *                         \
             : n_data_3D_double_init,         \
               unsigned int *                 \
             : n_data_3D_unsigned_int_init,   \
               short *               \
             : n_data_3D_short_init, \
               int *                          \
             : n_data_3D_int_init)(x, y, z, data)

#define n_data_2D_init(x, y, data)                                             \
    _Generic((data), double* : n_data_2D_double_init)(x, y, data)

#define n_data_init(...)                                                       \
    INIT_GET_MACRO(__VA_ARGS__, n_data_2D_init, n_data_3D_init,                \
                   n_data_4D_init)                                             \
    (__VA_ARGS__)

#define n_data_4D_assign(x, y, z, c, data, val)                                \
    _Generic((data),                     \
             double *                    \
             : n_data_4D_double_assign,    \
               int *                     \
             : n_data_4D_int_assign)(x, y, z, c, data, val)

#define n_data_3D_assign(x, y, z, data, val)                                   \
    _Generic((data),                          \
             double *                         \
             : n_data_3D_double_assign,         \
               unsigned int *                 \
             : n_data_3D_unsigned_int_assign,   \
               short *               \
             : n_data_3D_short_assign, \
               int *                          \
             : n_data_3D_int_assign)(x, y, z, data, val)

#define n_data_2D_assign(x, y, data, val)                                      \
    _Generic((data), double* : n_data_2D_double_assign)(x, y, data, val)

#define n_data_1D_assign(x, data, val)                                         \
    _Generic((data), double* : n_data_1D_double_assign)(x, data, val)

#define ASSIGN_GET_MACRO(_3, _4, _5, _6, NAME, ...) NAME
#define n_data_assign(...)                                                     \
    ASSIGN_GET_MACRO(__VA_ARGS__, n_data_1D_assign, n_data_2D_assign,          \
                     n_data_3D_assign, n_data_4D_assign)                       \
    (__VA_ARGS__)

#ifdef __cplusplus
}
#endif
#endif
