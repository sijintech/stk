#ifndef __NMATHFFTELASTIC_H__
#define __NMATHFFTELASTIC_H__

#include <ntextutils/ntextutils.h>
#include <nmathfft/fft.h>
#include <niobasic/niobasic.h>
#include <nmathbasic/array.h>
#include <nmathbasic/tensor.h>
#ifdef __cplusplus
extern "C"
{
#endif
#define ELASTICNAME 128

typedef struct{
    int control_solver_homo;
    int control_constrain_type; // 0 for strain, 1 for stress
    int control_print;
    int control_print_csv;
    int control_auto_index_update;
    int solver_index;
    int in_kspace;
    int phase_count;
    int index_map[3][3];

    int max_iterations;
    double error, threshold, total_energy;
    double stiffness_homo[3][3][3][3];
    double compliance_homo[3][3][3][3];
    double strain_avg[3][3];
    double stress_avg[3][3];
    char solver_name[ELASTICNAME];
    char csv_filename[ELASTICNAME];

    // link from fft
    double *kvec;
    int elastic_3d_nk[3];
    int kspace_totalsize, rspace_totalsize;
    int elastic_3d_n[3];

    // link from external array
    double *stiffness;
    double *displacement;
    double *stress;
    double *strain;
    double *strain_eigen;
    double *energy;
    short *phase;

    // assigned in the solver
    double *stiffness_delta;
    double *tmp;
    double *A_inverse;
    double *strain_heterogeneous;
    fftw_complex* k_tmp;
    fftw_complex* k_displacement;
    fftw_complex* k_rhs_homo;
    fftw_complex* k_rhs_inhomo;

    int iteration_index;
    int link_flag_stress;
    int link_flag_stiffness;
    int link_flag_strain;
    int link_flag_strain_eigen;
    int link_flag_displacement;
    int link_flag_energy;
    int link_phase;
    int set_flag_stiffness_homo;
    int set_flag_phase_count;
    int set_flag_constrain;
    int set_flag_strain_avg;
    int set_flag_stress_avg;
    NFFT nfft;
} NElasticSolver;
typedef NElasticSolver* NElasticSolverPtr;

// solver inhomo functions
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_update_inhomo_rhs_kspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_update_iterate_rhs_kspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solve_inhomo_kspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solve_inhomo_rspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solver_inhomo_bc_apply(NElasticSolverPtr esp);

// solver homo functions
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_update_homo_rhs_kspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solve_homo_kspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solve_homo_rspace(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_solver_homo_bc_apply(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_rhs_homo_kspace(NElasticSolverPtr esp);

// calculate functions
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_forward(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_backward(NElasticSolverPtr esp);
  NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_calculate_strain_heterogeneous(NElasticSolverPtr esp);

// print functions
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_print_screen(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_print_csv(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_print_csv_header(NElasticSolverPtr esp);

// criteria functions
   NMATHFFTPUBFUN int NMATHFFTPUBFUN n_fft_elastic_check_ready(NElasticSolverPtr esp);
   NMATHFFTPUBFUN double NMATHFFTPUBFUN n_fft_elastic_calculate_error(NElasticSolverPtr esp);
   NMATHFFTPUBFUN int NMATHFFTPUBFUN n_fft_elastic_converge(NElasticSolverPtr esp);

// data functions
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_string_set(NElasticSolverPtr esp,const char *name, const char *in);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_int_set(NElasticSolverPtr esp,const char *name, int in);
   NMATHFFTPUBFUN int  NMATHFFTPUBFUN n_fft_elastic_int_get(NElasticSolverPtr esp,const char *name);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_double_set(NElasticSolverPtr esp, const char *name, double in);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_double_array_set(NElasticSolverPtr esp,const char *name, double *in);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_short_array_link(NElasticSolverPtr esp, const char *name, short *in);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_double_array_link(NElasticSolverPtr esp, const char *name, double *in);

// setup functions
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_init(NElasticSolverPtr esp, NFFTPtr nfftptr);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_setup(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_reset(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_free(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_calculate_displacement(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_calculate_strain_total(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_calculate_stress(NElasticSolverPtr esp);
   NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_elastic_calculate_energy(NElasticSolverPtr esp);

#ifdef __cplusplus
}
#endif
#endif