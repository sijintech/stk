#include <nmathfft/poisson.h>

// This may be confusing, k_rhs_homo is the one used for both
// homo and inhomo, so in some sense this is the inhomo one
// I use this name because it is the one been used in homo solver
// While the k_rhs_inhomo is a place holder for the homo part
// of the inhomo rhs, the real inhomo rhs is still stored in
// k_rhs_homo.
// TODO: think about rename the k_rhs_homo and inhomo
//
void n_fft_poisson_rhs_inhomo_kspace(NPoissonSolverPtr psp)
{
    size_t k = 0;
    n_fft_poisson_rhs_homo_kspace(psp);
    for (k = 0; k < psp->kspace_totalsize; k++)
    {
        psp->k_rhs_inhomo[k] = psp->k_rhs_homo[k];
    }
}

// this will update the delta epsilon part of the inhomo rhs
// which will be updated each time in the iteration
void n_fft_poisson_rhs_iterate_kspace(NPoissonSolverPtr psp)
{
    int i = 0;
    int j = 0;
    size_t k = 0;
    int phase = 0;
    double(*delta)[psp->phase_count][3][3];
    delta = &NPTR2ARR3D(double, psp->epsilon_delta, psp->phase_count, 3, 3);

    memset(psp->k_tmp, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    memset(psp->k_rhs_homo, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    for (i = 0; i < 3; i++)
    {
        memset(psp->tmp, 0, sizeof(double) * psp->rspace_totalsize);
        for (j = 0; j < 3; j++)
        {
            // memcpy(psp->poisson_3d_tmp, psp->poisson_3d_epsilon_delta[i][j],
            // sizeof(double) * psp->rspace_totalsize); ZF_LOGI("The delta by
            // phase is %i %i %i %f %f", phase, i, j, (*delta)[0][i][j],
            // (*delta)[0][i][j]);
            for (k = 0; k < psp->rspace_totalsize; k++)
            {
                phase = psp->phase[k];
                psp->tmp[k] =
                    psp->tmp[k] + (*delta)[phase][i][j] * psp->field[3 * k + j];
            }
        }
        n_fftw_r2c_3d_forward(&psp->nfft, psp->tmp, psp->k_tmp);
        for (k = 0; k < psp->kspace_totalsize; k++)
        {
            psp->k_rhs_homo[k] =
                psp->k_rhs_homo[k] + psp->kvec[3 * k + i] * I * psp->k_tmp[k];
        }
    }

    for (k = 0; k < psp->kspace_totalsize; k++)
    {
        psp->k_rhs_homo[k] = psp->k_rhs_inhomo[k] - psp->k_rhs_homo[k];
    }
}

void n_fft_poisson_solve_inhomo_kspace(NPoissonSolverPtr psp)
{
    size_t i = 0;
    n_fft_poisson_calculate_field_kspace(psp);

    for (i = 0; i < psp->max_iterations; i++)
    {
        n_fft_poisson_rhs_iterate_kspace(psp);
        n_fft_poisson_solve_homo_kspace(psp);
        psp->iteration_index = psp->iteration_index + 1;
        n_fft_poisson_calculate_field_kspace(psp);
        n_fft_poisson_calculate_energy(psp);
        n_fft_poisson_calculate_error(psp);
        if (psp->control_print == 1)
            n_fft_poisson_3d_print(psp);
        if (psp->control_print_csv == 1)
            n_fft_poisson_3d_print_csv(psp);
        if (n_fft_poisson_converge(psp) == 1)
            break;
    }
    if (psp->control_auto_index_update)
        psp->solver_index = psp->solver_index + 1;
}

void n_fft_poisson_solve_inhomo_rspace(NPoissonSolverPtr psp)
{
    if (n_fft_poisson_check_ready(psp) != 1)
    {
        ZF_LOGE("Something is missing");
    }

    // ZF_LOGI("The solve inhomo rspace %i
    // %i",poisson_3d_control_print,poisson_3d_control_print_csv); remember to
    // call the init first
    if (psp->control_print == 1)
    {
        ZF_LOGI("---------- Inhom Poisson Solver for %s Begin ----------",
                psp->solver_name);
    }
    if (psp->control_print_csv == 1)
    {
        const char* header = "solver_index,iteration,error";
        n_timeFile_write_header_line(header, psp->csv_filename);
    }
    n_fft_poisson_forward(psp);
    n_fft_poisson_rhs_inhomo_kspace(psp);
    n_fft_poisson_solve_inhomo_kspace(psp);
    n_fft_poisson_backward(psp);
    // n_fftw_r2c_3d_backward(psp->poisson_3d_k_potential,
    // psp->poisson_3d_potential);
    psp->iteration_index = 0;
    if (psp->control_print == 1)
    {
        ZF_LOGI("----------- Inhomo Poisson Solver for %s End -----------",
                psp->solver_name);
    }
}
