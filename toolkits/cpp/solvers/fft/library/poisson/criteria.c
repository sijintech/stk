#include "nmathfft/poisson.h"

int n_fft_poisson_check_ready(NPoissonSolverPtr psp)
{
    int check = 1;
    if (psp->link_flag_potential == 0)
    {
        check = 0;
        ZF_LOGE("The potential for solver %s is not linked.", psp->solver_name);
    }
    if (psp->link_flag_epsilon == 0)
    {
        check = 0;
        ZF_LOGE("The epsilon for solver %s is not linked.", psp->solver_name);
    }
    if (psp->link_flag_field == 0)
    {
        check = 0;
        ZF_LOGE("The electric field distribution of solver %s is not linked.",
                psp->solver_name);
    }
    if (psp->link_flag_rhs_source == 0)
    {
        check = 0;
        ZF_LOGE("The rhs source term distribution of solver %s is not linked.",
                psp->solver_name);
    }
    if (psp->link_phase == 0)
    {
        check = 0;
        ZF_LOGE("The material phase distribution for solver %s is not linked.",
                psp->solver_name);
    }
    if (psp->set_flag_epsilon_homo == 0)
    {
        check = 0;
        ZF_LOGE("The homogeneous part of epsilon for solver %s is not set.",
                psp->solver_name);
    }
    if (psp->set_flag_external_field == 0)
    {
        check = 0;
        ZF_LOGE("The external applied field for solver %s is not set.",
                psp->solver_name);
    }
    if (psp->set_flag_phase_count == 0)
    {
        check = 0;
        ZF_LOGE("The total number of phases for solver %s is not set.",
                psp->solver_name);
    }

    return check;
}

void n_fft_poisson_calculate_energy(NPoissonSolverPtr psp)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    int index = 0;
    double(*epsilon)[psp->phase_count][3][3];
    epsilon = &NPTR2ARR3D(double, psp->epsilon, psp->phase_count, 3, 3);
    for (i = 0; i < psp->rspace_totalsize; i++)
    {
        psp->energy[i] = 0;
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                index = 6 * i + psp->index_map[j][k];
                psp->energy[i] =
                    psp->energy[i] + (*epsilon)[psp->phase[i]][j][k] *
                                         psp->field[3 * i + j] *
                                         psp->field[3 * i + k];
            }
        }
    }
}

// void n_fft_poisson_calculate_error(NPoissonSolverPtr psp){
//     memcpy(psp->tmp,psp->potential,sizeof(double)*psp->rspace_totalsize);
//     // ZF_LOGI("the potential 0 %f %f",psp->potential[0] ,psp->tmp[0]);
//     n_fft_backward(&psp->nfft, "r2c_3d", psp->k_potential, psp->potential);
//     // ZF_LOGI("the potential 10 %f %f",psp->potential[10] ,psp->tmp[10]);
//     psp->error = 0;
//     double temp=0;
//     for (size_t i = 1; i < psp->rspace_totalsize; i++)
//     {
//         temp = fabs(psp->potential[i] - psp->tmp[i]) /
//         fabs(psp->potential[i])  ; if (psp->error < temp &&
//         fabs(psp->potential[i])>1e-15)
//         {
//             psp->error = temp;
//         }
//     }
// }

void n_fft_poisson_calculate_error(NPoissonSolverPtr psp)
{
    psp->error = 0;
    double temp = 0;
    size_t i = 0;
    for (i = 1; i < psp->rspace_totalsize; i++)
    {
        temp = temp + psp->energy[i];
    }
    psp->error = fabs(psp->total_energy - temp) / fabs(psp->total_energy);
    psp->total_energy = temp;
    if (fabs(temp) < 1e-16)
    {
        psp->error = 0;
    }
}

int n_fft_poisson_converge(NPoissonSolverPtr psp)
{
    if (psp->error < psp->threshold)
    {
        ZF_LOGI("Converged, error: %13.6le, threshold: %13.6le", psp->error,
                psp->threshold);
        return 1;
    }
    else
    {
        return 0;
    }
}