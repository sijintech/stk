#include <niobasic/niobasic.h>
#include <nmathfft/fft.h>
#include <ntextutils/ntextutils.h>
#include <zf_log.h>

#ifndef __NMATHFFTPOISSON_H__
#define __NMATHFFTPOISSON_H__

#ifdef __cplusplus
extern "C"
{
#endif
#define POISSONNAME 128
    typedef struct
    {
        // These are variables to be set from outside
        int control_rhs_source_nonzero;
        int control_solver_homo;
        int control_external_field_nonzero;
        int control_auto_index_update;
        int control_print;
        int control_print_csv;
        int solver_index;
        int in_kspace;
        int phase_count;
        double iter_step;

        int max_iterations;
        double error, threshold, total_energy;
        double epsilon_homo[3][3];
        double external_field[3];
        char solver_name[POISSONNAME];
        char csv_filename[POISSONNAME];
        // The following are linked with array or value from fft setup
        double* kvec;
        int nk[3];
        int kspace_totalsize, rspace_totalsize;
        int n[3];
        int index_map[3][3];

        // The following are linked with external array
        // double *poisson_3d_epsilon[3][3]; // this is an array of pointer,
        // which point to the actual epsilon use defined
        double* epsilon;   // for \delta\epsilon_{ij}, only delta is needed for
                           // calculation
        double* potential; // this is a scalar, such as the electric potential
        double* field; // this is the gradient of the potential field, such as
                       // the electric field
        double* rhs_source; // the right hand side of the equation, which
                            // includes the free charge
        short* phase;
        double* energy;

        // The following is allocated in the solver
        // memory for each array should be
        // nx*ny*nz*8/1e6 = 8mb for 100 cube
        // estimated total should around 50mb
        double* epsilon_delta; // for \delta\epsilon_{ij}, only delta is needed
                               // for calculation
        double* tmp;           // for real space random usage, 1Gb per 512 cube
        fftw_complex* k_tmp;   // for k space random usage, 1Gb per 512 cube
        fftw_complex* k_rhs_homo;
        fftw_complex* k_rhs_inhomo; // for \Tilde{\rho} + E^{ext}_{i}k_j I
                                    // \Tilde{\delta \epsilon_{ij}}, 1Gb
        double* A_inverse; // for \frac{1}{\bar{\epsilon}_{ij} k_i k_j}, 1Gb
        fftw_complex* k_potential; // 1Gb
        fftw_complex k_epsilon_homo[3][3];

        int iteration_index;
        int link_flag_potential;
        int link_flag_epsilon;
        int link_flag_field;
        int link_flag_rhs_source;
        int link_flag_energy;
        int link_phase;
        int set_flag_epsilon_homo;
        int set_flag_phase_count;
        int set_flag_external_field;
        NFFT nfft;
    } NPoissonSolver;
    typedef NPoissonSolver* NPoissonSolverPtr;

    // data
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_string_set(
        NPoissonSolverPtr psp, const char* name, const char* in);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_int_set(NPoissonSolverPtr psp, const char* name, int in);
    NMATHFFTPUBFUN int NMATHFFTPUBFUN
    n_fft_poisson_int_get(NPoissonSolverPtr psp, const char* name);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_double_set(
        NPoissonSolverPtr psp, const char* name, double in);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_double_array_set(
        NPoissonSolverPtr psp, const char* name, double* in);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_double_array_link(
        NPoissonSolverPtr psp, const char* name, double* in);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_short_array_link(
        NPoissonSolverPtr psp, const char* name, short* in);

    // setup
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_init(NPoissonSolverPtr ptr,
                                                          NFFTPtr nfftptr);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN n_fft_poisson_free(NPoissonSolverPtr);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_setup(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_reset(NPoissonSolverPtr psp);

    // calc
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_forward(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_backward(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_calculate_field_kspace(NPoissonSolverPtr psp);
    // NMATHFFTPUBFUN void NMATHFFTPUBFUN
    // n_fft_poisson_calculate_potential_gradient_kspace(NPoissonSolverPtr psp);

    // solver inhomo
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_solve_inhomo_rspace(NPoissonSolverPtr psp);
    // NMATHFFTPUBFUN void NMATHFFTPUBFUN
    // n_fft_poisson_rhs_inhomo_kspace(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_rhs_iterate_kspace(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_solve_inhomo_kspace(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_rhs_homo_kspace(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_solve_homo_kspace(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_solve_homo_rspace(NPoissonSolverPtr psp);

    // criteria
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_calculate_energy(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_calculate_error(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN int NMATHFFTPUBFUN
    n_fft_poisson_converge(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN int NMATHFFTPUBFUN
    n_fft_poisson_check_ready(NPoissonSolverPtr psp);

    // print
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_3d_print(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_3d_print_csv(NPoissonSolverPtr psp);
    NMATHFFTPUBFUN void NMATHFFTPUBFUN
    n_fft_poisson_3d_print_csv_header(NPoissonSolverPtr psp);

#define n_fft_poisson_data_set(psp, name, in)                                  \
    _Generic((in),                              \
           double *                           \
           : n_fft_poisson_double_array_set,  \
             char *                           \
           : n_fft_poisson_string_set,        \
             int                              \
           : n_fft_poisson_int_set,           \
             double                           \
           : n_fft_poisson_double_set)(psp, name, in)

#define n_fft_poisson_data_link(psp, name, in)                                 \
    _Generic((in),                               \
           double *                            \
           : n_fft_poisson_double_array_link,  \
             short *                           \
           : n_fft_poisson_short_array_link)(psp, name, in)

#ifdef __cplusplus
}
#endif

#endif