#ifndef __NMATHFFTFFT_H__
#define __NMATHFFTFFT_H__

#include <complex.h>
#include <fftw/fftw3.h>
#include <math.h>
#include <nmathfft/errors.h>
#include <nmathfft/exports.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zf_log.h>
// #include <stddef.h>
/**
 * For all function I/O interfaces, we use RAD value, user need to transform
 * from degree to RAD themselves.
 */

#ifdef __cplusplus
extern "C"
{
#endif

    typedef struct
    {
        int nx, ny, nz;
        double dx, dy, dz;
        int nkx, nky, nkz;
        int totalsize, totalksize;
        double* kvec;
        fftw_plan planFWD, planBWD;
        double *rin, *rout;
        fftw_complex *cin, *cout;
    } NFFT;
    typedef NFFT* NFFTPtr;

    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_assign_zero(fftw_complex* x);

    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_data_3D_complex_init(
        int x, int y, int z, fftw_complex (**outptr)[x][y][z]);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_data_3D_complex_fill(int x, int y, int z, fftw_complex array[x][y][z]);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_data_3D_complex_print(int x, int y, int z, fftw_complex array[x][y][z]);

    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_data_1D_complex_add(int n, fftw_complex out[n], fftw_complex in[n]);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_data_complex_get_nth_component(
        int total, int rank, int nth, fftw_complex out[total],
        fftw_complex in[total][rank]);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_data_complex_set_nth_component(
        int total, int rank, int nth, fftw_complex out[total][rank],
        fftw_complex in[total]);

    //   NMATHFFTPUBFUN  void NMATHFFTCALL n_fft_int_data_set_f(const char
    //   *name,  int **in);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_data_int_array_set(NFFTPtr fftptr,
                                                              const char* name,
                                                              int* in);
    //   NMATHFFTPUBFUN void NMATHFFTCALL n_fft_double_data_set_f(const char
    //   *name, double
    //   **in);
    NMATHFFTPUBFUN void NMATHFFTCALL
    n_fft_data_double_array_set(NFFTPtr fftptr, const char* name, double* in);

    // NMATHFFTPUBFUN void NMATHFFTCALL n_fft_int_data_get_f(const char *name,
    // int **in);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_data_int_array_get(NFFTPtr fftptr,
                                                              const char* name,
                                                              int* in);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_data_int_get(NFFTPtr fftptr,
                                                        const char* name,
                                                        int* in);
    // NMATHFFTPUBFUN void NMATHFFTCALL n_fft_double_data_get_f(const char
    // *name, double **out);
    NMATHFFTPUBFUN void NMATHFFTCALL
    n_fft_data_double_array_get(NFFTPtr fftptr, const char* name, double* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_data_double_array_link(
        NFFTPtr fftptr, const char* name, double** out);

    //   NMATHFFTPUBFUN  void NMATHFFTCALL n_fftw_r2c_3d_int_data_set3_f(const
    //   char *name, int *n, int **in); NMATHFFTPUBFUN void NMATHFFTCALL
    //   n_fftw_r2c_3d_double_data_set3_f(const char *name, int *n, double
    //   **in);
    NMATHFFTPUBFUN void NMATHFFTCALL
    n_fftw_r2c_3d_data_int_array_set(NFFTPtr fftptr, const char* name, int* in);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_data_double_array_set(
        NFFTPtr fftptr, const char* name, double* in);

    //   NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_int_data_get3_f(const
    //   char *name, int *n, int **out); NMATHFFTPUBFUN void NMATHFFTCALL
    //   n_fftw_r2c_3d_double_data_get1d_f(const char *name, int *n, double
    //   **out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_data_int_array_get(
        NFFTPtr fftptr, const char* name, int* out);
    // NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_data_int_get(NFFTPtr
    // fftptr, const char *name, int *in);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_data_double_array_link(
        NFFTPtr fftptr, const char* name, double** out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_data_double_array_get(
        NFFTPtr fftptr, const char* name, double* out);

    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_setup(NFFTPtr fftptr,
                                                 const char* name);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_setup(NFFTPtr fftptr);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_free(NFFTPtr fftptr,
                                                const char* name);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_free(NFFTPtr fftptr);

    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_backward(NFFTPtr fftptr,
                                                            fftw_complex* in,
                                                            double* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_forward(NFFTPtr fftptr,
                                                           double* in,
                                                           fftw_complex* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_n3d_backward(NFFTPtr fftptr,
                                                             int n,
                                                             fftw_complex* in,
                                                             double* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_n3d_forward(NFFTPtr fftptr,
                                                            int n, double* in,
                                                            fftw_complex* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_derivative(NFFTPtr fftptr,
                                                              const char* axis,
                                                              double* in,
                                                              double* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_derivative_kspace(
        NFFTPtr fftptr, const char* name, fftw_complex* in, fftw_complex* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_derivative_nth_kspace(
        NFFTPtr fftptr, const char* name, int rank, int nth, fftw_complex* in,
        fftw_complex* out);
    // NMATHFFTPUBFUN void NMATHFFTCALL n_fftw_r2c_3d_derivative_y(double *in,
    // double *out); NMATHFFTPUBFUN void NMATHFFTCALL
    // n_fftw_r2c_3d_derivative_z(double *in, double *out);

    // NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_backward_f(const char *name,
    // fftw_complex **in, double **out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_backward(NFFTPtr fftptr,
                                                        const char* name,
                                                        fftw_complex* in,
                                                        double* out);
    // NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_forward_f(const char *name,
    // double **in, fftw_complex **out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_forward(NFFTPtr fftptr,
                                                       const char* name,
                                                       double* in,
                                                       fftw_complex* out);
    // NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_derivative_f(const char *name,
    // double **in, double **out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_derivative(NFFTPtr fftptr,
                                                          const char* name,
                                                          double* in,
                                                          double* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_derivative_kspace(
        NFFTPtr fftptr, const char* name, fftw_complex* in, fftw_complex* out);
    NMATHFFTPUBFUN void NMATHFFTCALL n_fft_r2c_derivative_nth_kspace(
        NFFTPtr fftptr, const char* name, int rank, int nth, fftw_complex* in,
        fftw_complex* out);

#define n_fft_data_set(fftptr, name, in)                                       \
    _Generic((in),                         \
           int *                         \
           : n_fft_data_int_array_set,   \
             double *                    \
           : n_fft_data_double_array_set)(fftptr, name, in)

#define n_fft_data_get(fftptr, name, out)                                      \
    _Generic((out), int* : n_fft_data_int_array_get)(fftptr, name, out)

#define n_fft_data_link(fftptr, name, out)                                     \
    _Generic((out), double** : n_fft_data_double_array_link)(fftptr, name, out)

#define n_fft_forward(fftptr, name, in, out)                                   \
    _Generic((in),                             \
           double *                          \
           : _Generic((out), fftw_complex *  \
                      : n_fft_r2c_forward))(fftptr, name, in, out)

#define n_fft_backward(fftptr, name, in, out)                                  \
    _Generic((in),                              \
           fftw_complex *                     \
           : _Generic((out), double *         \
                      : n_fft_r2c_backward))(fftptr, name, in, out)

#define n_fft_derivative(fftptr, name, in, out)                                \
    _Generic((in), double* : n_fft_r2c_derivative)(fftptr, name, in, out)

#ifdef __cplusplus
}
#endif

#endif