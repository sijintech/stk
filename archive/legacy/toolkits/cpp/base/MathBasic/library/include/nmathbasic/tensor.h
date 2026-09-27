

#ifndef __NMATHBASICTENSOR_H__
#define __NMATHBASICTENSOR_H__

#include <nmathbasic/errors.h>
#include <nmathbasic/exports.h>
#include <ntextutils/ntextutils.h>
// #include <nmathbasic/lapack.h>
#ifdef __cplusplus
extern "C"
{
#endif

    NMATHBASICPUBFUN void NMATHBASICCALL n_tensor_rank2_from_voigt_f(
        int* x, int* y, int* z, double** voigt, double** tensor, int* isStrain);
    NMATHBASICPUBFUN void NMATHBASICCALL n_tensor_rank2_to_voigt_f(
        int* x, int* y, int* z, double** tensor, double** voigt, int* isStrain);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank2_from_voigt(int x, int y, int z, double voigt[x][y][z][6],
                              double tensor[x][y][z][3][3], int isStrain);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank2_to_voigt(int x, int y, int z, double tensor[x][y][z][3][3],
                            double voigt[x][y][z][6], int isStrain);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor3333_inverse66(double out[3][3][3][3], double in[3][3][3][3]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor3333_inverse99(double out[3][3][3][3], double in[3][3][3][3]);
    NMATHBASICPUBFUN void NMATHBASICCALL n_tensor3333_mult_tensor33(
        double out[3][3], double A[3][3][3][3], double B[3][3]);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor3333_to_tensor66(double out[6][6], double in[3][3][3][3]);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank2_print_screen(const char* name, double* input);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank2_print_file(const char* name, double* input);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank4_print_screen(const char* name, double* input);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank4_print_file(const char* name, double* input);

    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank12_print_screen(const char* name, double* input);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank12_print_file(const char* name, double* input);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank21_print_screen(const char* name, double* input);
    NMATHBASICPUBFUN void NMATHBASICCALL
    n_tensor_rank21_print_file(const char* name, double* input);
#ifdef __cplusplus
}
#endif
#endif
