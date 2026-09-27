#include <fftw/fftw3.h>
// #include <fftw/fftw3_mkl.h>
#include <nmathfft/cahnhilliard.h>

// init should be called only once, as long as the homo part is the same
// the data array linking should happen before the init
void n_fft_cahnhilliard_init(NCHSolverPtr chsp, NFFTPtr nfftptr)
{

    chsp->nfft = *nfftptr;

    strcpy(chsp->solver_name, "cahnhilliard");

    chsp->link_flag_driving_force = 0;
    chsp->link_flag_composition = 0;

    chsp->in_kspace = 0; // 0 means in rsapce, 1 in kspace;

    // ZF_LOGI("chsp setup");
    n_fft_data_get(nfftptr, "r2c_3d/totalksize", &(chsp->kspace_totalsize));
    n_fft_data_get(nfftptr, "r2c_3d/totalsize", &(chsp->rspace_totalsize));
    n_fft_data_link(nfftptr, "r2c_3d/kvector", &(chsp->kvec));
    chsp->tmp = calloc(chsp->rspace_totalsize, sizeof(double));
    chsp->lhs = calloc(chsp->kspace_totalsize, sizeof(double));
    chsp->kpow2 = calloc(chsp->kspace_totalsize, sizeof(double));
    chsp->kpow4 = calloc(chsp->kspace_totalsize, sizeof(double));
    chsp->k_tmp = (fftw_complex*)fftw_malloc(chsp->kspace_totalsize *
                                             sizeof(fftw_complex));
    chsp->k_composition = (fftw_complex*)fftw_malloc(chsp->kspace_totalsize *
                                                     sizeof(fftw_complex));
    chsp->k_driving_force = (fftw_complex*)fftw_malloc(chsp->kspace_totalsize *
                                                       sizeof(fftw_complex));
    size_t i = 0;
    for (i = 0; i < chsp->kspace_totalsize; i++)
    {
        n_fft_assign_zero(&chsp->k_tmp[i]);
        n_fft_assign_zero(&chsp->k_composition[i]);
        n_fft_assign_zero(&chsp->k_driving_force[i]);
        // memcpy(chsp->k_tmp[i], 0, sizeof(fftw_complex));
        // memcpy(chsp->k_composition[i], 0, sizeof(fftw_complex));
        // memcpy(chsp->k_driving_force[i], 0, sizeof(fftw_complex));
        // Use be able to work like this
        // chsp->k_driving_force[i] = 0 + 0 * I;

        chsp->kpow2[i] = (chsp->kvec[3 * i] * chsp->kvec[3 * i] +
                          chsp->kvec[3 * i + 1] * chsp->kvec[3 * i + 1] +
                          chsp->kvec[3 * i + 2] * chsp->kvec[3 * i + 2]);
        chsp->kpow4[i] = chsp->kpow2[i] * chsp->kpow2[i];
    }
}

void n_fft_cahnhilliard_setup(NCHSolverPtr chsp)
{
    size_t i = 0;
    for (i = 0; i < chsp->kspace_totalsize; i++)
    {
        chsp->lhs[i] = 1 + chsp->M * chsp->kappa * chsp->dt * chsp->kpow4[i];
    }
}

void n_fft_cahnhilliard_reset(NCHSolverPtr chsp)
{
    // memset(chsp->k_tmp, 0, sizeof(fftw_complex) * chsp->kspace_totalsize);
    // memset(chsp->k_driving_force, 0, sizeof(fftw_complex) *
    // chsp->kspace_totalsize); memset(chsp->k_composition, 0,
    // sizeof(fftw_complex) * chsp->kspace_totalsize); memset(chsp->tmp, 0,
    // sizeof(double) * chsp->rspace_totalsize); memset(chsp->lhs, 0,
    // sizeof(double) * chsp->rspace_totalsize); memset(chsp->composition, 0,
    // sizeof(double) * chsp->rspace_totalsize); memset(chsp->driving_force, 0,
    // sizeof(double) * chsp->rspace_totalsize);
}

void n_fft_cahnhilliard_free(NCHSolverPtr chsp)
{
    free(chsp->tmp);
    free(chsp->lhs);
    free(chsp->kpow2);
    free(chsp->kpow4);
    fftw_free(chsp->k_tmp);
    fftw_free(chsp->k_driving_force);
    fftw_free(chsp->k_composition);
    // poisson_3d_control_epsilon_delta_nonzero = 1;
    // poisson_3d_control_external_field_nonzero = 1;
    // poisson_3d_control_rhs_source_nonzero = 1;
    // poisson_3d_solver_index=0;
    // poisson_3d_iteration_index=0;
    free(chsp);
}
