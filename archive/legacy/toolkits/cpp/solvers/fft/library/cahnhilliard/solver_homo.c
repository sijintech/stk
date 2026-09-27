#include <nmathfft/cahnhilliard.h>

void n_fft_cahnhilliard_rhs_homo_kspace(NCHSolverPtr chsp)
{

}

void n_fft_cahnhilliard_solve_homo_kspace(NCHSolverPtr chsp)
{
    size_t k=0;
    for (k = 0; k < chsp->kspace_totalsize; k++)
    {
        chsp->k_composition[k] = (chsp->k_composition[k] - chsp->M*chsp->dt*chsp->kpow2[k]*chsp->k_driving_force[k]) / chsp->lhs[k];
    }
}

void n_fft_cahnhilliard_solve_homo_rspace(NCHSolverPtr chsp)
{
    // need to fix the
    if (n_fft_cahnhilliard_check_ready(chsp) != 1)
    {
        ZF_LOGE("Something is missing");
    }

    // remember to call the init first

    n_fft_cahnhilliard_forward(chsp);
    n_fft_cahnhilliard_rhs_homo_kspace(chsp);
    n_fft_cahnhilliard_solve_homo_kspace(chsp);
    n_fft_cahnhilliard_backward(chsp);
}
