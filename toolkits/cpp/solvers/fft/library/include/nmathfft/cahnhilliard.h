#ifndef __NCAHNHILLIARD_H__
#define __NCAHNHILLIARD_H__

#include <nmathfft/fft.h>

#ifdef __cplusplus
extern "C"
{
#endif
#define CHNAME 128

    // Double precision

    typedef struct
    {
        char solver_name[CHNAME];
        // These are set from outside
        double *composition;
        double *driving_force;
        double M;
        double kappa;
        double c0;
        double dt;
        double *kvec;
        int nk[3];
        int kspace_totalsize, rspace_totalsize;
        int n[3];

        // These are allocated inside
        double *lhs;
        double *tmp;
        double *kpow2;
        double *kpow4;
        fftw_complex *k_tmp;
        fftw_complex *k_composition;
        fftw_complex *k_driving_force;
        NFFT nfft;

        int link_flag_driving_force;
        int link_flag_composition;
        int in_kspace;
    } NCHSolver;
    typedef NCHSolver *NCHSolverPtr;

  //data
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_string_set(NCHSolverPtr chsp, const char *name, const char *in);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_int_set(NCHSolverPtr chsp, const char *name, int in);
  NMATHFFTPUBFUN int  NMATHFFTPUBFUN n_fft_cahnhilliard_int_get(NCHSolverPtr chsp, const char *name);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_double_set(NCHSolverPtr chsp, const char *name, double in);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_double_array_set(NCHSolverPtr chsp, const char *name, double *in);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_double_array_link(NCHSolverPtr chsp, const char *name, double *in);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_short_array_link(NCHSolverPtr chsp, const char *name, short *in);

  //setup
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_init(NCHSolverPtr chsp, NFFTPtr nfftptr);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_free(NCHSolverPtr chsp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_setup(NCHSolverPtr chsp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_reset(NCHSolverPtr chsp);

  //calc
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_forward(NCHSolverPtr chsp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_backward(NCHSolverPtr chsp);
  // solver inhomo
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_rhs_homo_kspace(NCHSolverPtr chsp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_solve_homo_kspace(NCHSolverPtr chsp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_cahnhilliard_solve_homo_rspace(NCHSolverPtr chsp);

  // criteria
  NMATHFFTPUBFUN int NMATHFFTPUBFUN n_fft_cahnhilliard_check_ready(NCHSolverPtr chsp);


#define n_fft_cahnhilliard_data_set(psp, name, in) \
  _Generic((in),                              \
           double *                           \
           : n_fft_cahnhilliard_double_array_set,  \
             char *                           \
           : n_fft_cahnhilliard_string_set,        \
             int                              \
           : n_fft_cahnhilliard_int_set,           \
             double                           \
           : n_fft_cahnhilliard_double_set)(psp, name, in)

#define n_fft_cahnhilliard_data_link(psp, name, in) \
  _Generic((in),                               \
           double *                            \
           : n_fft_cahnhilliard_double_array_link,  \
             short *                           \
           : n_fft_cahnhilliard_short_array_link)(psp, name, in)


#ifdef __cplusplus
}
#endif
#endif /*__TIMEFILE_H__*/
