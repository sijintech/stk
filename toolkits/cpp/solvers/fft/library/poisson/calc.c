#include <nmathfft/poisson.h>

void n_fft_poisson_forward(NPoissonSolverPtr psp)
{
    n_fftw_r2c_3d_forward(&psp->nfft, psp->potential, psp->k_potential);
    psp->in_kspace = 1;
}

void n_fft_poisson_backward(NPoissonSolverPtr psp)
{
    // ZF_LOGI("the backward %p %p",psp->poisson_3d_k_potential, psp->poisson_3d_potential);
    n_fft_backward(&psp->nfft, "r2c_3d", psp->k_potential, psp->potential);
    psp->in_kspace = 0;
}

void n_fft_poisson_calculate_field_kspace(NPoissonSolverPtr psp)
{
    size_t i=0;
    size_t j=0;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < psp->kspace_totalsize; j++)
        {
            psp->k_tmp[j] = psp->kvec[3 * j + i] * I * psp->k_potential[j];
        }
        n_fftw_r2c_3d_backward(&psp->nfft, psp->k_tmp, psp->tmp);
        for (j = 0; j < psp->rspace_totalsize; j++)
        {
            psp->field[3 * j + i] = - psp->tmp[j] + psp->external_field[i];
            // ZF_LOGI("The electric field %i %i %f",j,i,poisson_3d_field[3 * j + i]);
        }
    }
}