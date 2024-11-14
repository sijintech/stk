#include "nmathfft/poisson.h"

void n_fft_poisson_rhs_homo_kspace(NPoissonSolverPtr psp)
{
    memset(psp->k_rhs_homo, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    n_fftw_r2c_3d_forward(&psp->nfft, psp->rhs_source, psp->k_rhs_homo);
}

void n_fft_poisson_solve_homo_kspace(NPoissonSolverPtr psp)
{
    size_t k = 0;
    // fftw_complex prev;
    for (k = 0; k < psp->kspace_totalsize; k++)
    {
        // prev = psp->k_potential[k] ;
        // psp->k_potential[k] = psp->A_inverse[k] * psp->k_rhs_homo[k];
        // psp->k_potential[k] = psp->iter_step*psp->k_potential[k]  +
        // (1-psp->iter_step)*prev;
        psp->k_potential[k] =
            psp->iter_step * psp->A_inverse[k] * psp->k_rhs_homo[k] +
            (1 - psp->iter_step) * psp->k_potential[k];
    }
    // memcpy(psp->tmp,psp->potential,psp->rspace_totalsize*sizeof(double));
    // n_fft_backward(&psp->nfft, "r2c_3d", psp->k_potential, psp->potential);
    // for(k=0;k<psp->rspace_totalsize;k++){
    //     psp->potential[k] = psp->iter_step*psp->potential[k] +
    //     (1-psp->iter_step)*psp->tmp[k];
    // }
    // n_fftw_r2c_3d_forward(&psp->nfft, psp->potential, psp->k_potential);
}

void n_fft_poisson_solve_homo_rspace(NPoissonSolverPtr psp)
{
    // need to fix the
    if (n_fft_poisson_check_ready(psp) != 1)
    {
        ZF_LOGE("Something is missing");
    }

    // remember to call the init first
    // ZF_LOGI("The solve inhomo rspace %i
    // %i",poisson_3d_control_print,poisson_3d_control_print_csv);
    if (psp->control_print == 1)
    {
        ZF_LOGI("---------- Homo Poisson Solver for %s Begin ----------",
                psp->solver_name);
    }
    if (psp->control_print_csv == 1)
    {
        const char* header = "solver_index,iteration,error";
        n_timeFile_write_line_from_string(header, psp->csv_filename);
    }
    n_fft_poisson_forward(psp);
    n_fft_poisson_rhs_homo_kspace(psp);
    n_fft_poisson_solve_homo_kspace(psp);
    n_fft_poisson_backward(psp);
    // n_fftw_r2c_3d_backward(psp->poisson_3d_k_potential,
    // psp->poisson_3d_potential);
    psp->iteration_index = 0;
    if (psp->control_print == 1)
    {
        ZF_LOGI("----------- Homo Poisson Solver for %s End -----------",
                psp->solver_name);
    }
}
