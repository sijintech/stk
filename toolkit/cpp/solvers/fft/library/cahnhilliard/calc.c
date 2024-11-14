#include <nmathfft/cahnhilliard.h>

void n_fft_cahnhilliard_forward(NCHSolverPtr chsp)
{
    n_fftw_r2c_3d_forward(&chsp->nfft, chsp->composition, chsp->k_composition);
    n_fftw_r2c_3d_forward(&chsp->nfft, chsp->driving_force, chsp->k_driving_force);
    chsp->in_kspace = 1;
}

void n_fft_cahnhilliard_backward(NCHSolverPtr chsp)
{
    // ZF_LOGI("the backward %p %p",psp->poisson_3d_k_potential, psp->poisson_3d_potential);
    n_fft_backward(&chsp->nfft, "r2c_3d", chsp->k_composition, chsp->composition);
    chsp->in_kspace = 0;
}
