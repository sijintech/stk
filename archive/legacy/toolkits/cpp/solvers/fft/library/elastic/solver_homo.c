#include "nmathfft/elastic.h"

void n_fft_elastic_rhs_homo_kspace(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;
    double(*kvec)[esp->kspace_totalsize][3];
    kvec = &NPTR2ARR2D(double, esp->kvec, esp->kspace_totalsize, 3);
    double(*delta)[esp->phase_count][3][3][3][3];
    double(*stiff)[esp->phase_count][3][3][3][3];
    double(*eigen)[esp->rspace_totalsize][6];
    fftw_complex(*k_rhs)[esp->kspace_totalsize][3];
    int phase;
    delta =
        &NPTR2ARR5D(double, esp->stiffness_delta, esp->phase_count, 3, 3, 3, 3);
    stiff = &NPTR2ARR5D(double, esp->stiffness, esp->phase_count, 3, 3, 3, 3);
    eigen = &NPTR2ARR2D(double, esp->strain_eigen, esp->rspace_totalsize, 6);
    k_rhs =
        &NPTR2ARR2D(fftw_complex, esp->k_rhs_homo, esp->kspace_totalsize, 3);
    memset(esp->k_rhs_homo, 0,
           sizeof(fftw_complex) * esp->kspace_totalsize * 3);
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            memset(esp->tmp, 0, sizeof(double) * esp->rspace_totalsize);
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    for (m = 0; m < esp->rspace_totalsize; m++)
                    {
                        phase = esp->phase[m];
                        esp->tmp[m] =
                            esp->tmp[m] + (*stiff)[phase][i][j][k][l] *
                                              (*eigen)[m][esp->index_map[k][l]];
                    }
                }
            }
            n_fft_forward(&esp->nfft, "r2c_3d", esp->tmp, esp->k_tmp);
            for (m = 0; m < esp->kspace_totalsize; m++)
            {
                (*k_rhs)[m][i] = (*k_rhs)[m][i] - (*kvec)[m][j] * esp->k_tmp[m];
            }
        }
    }
    // ZF_LOGI("rhs homo k %f+%f*i", creal(esp->k_rhs_homo[100]),
    //         cimag(esp->k_rhs_homo[100]));
}

void n_fft_elastic_solve_homo_kspace(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t k = 0;
    size_t m = 0;
    double(*inv)[esp->kspace_totalsize][6];
    inv = &NPTR2ARR2D(double, esp->A_inverse, esp->kspace_totalsize, 6);
    for (m = 0; m < esp->kspace_totalsize; m++)
    {
        for (k = 0; k < 3; k++)
        {
            esp->k_displacement[3 * m + k] = 0 + 0 * I;
            for (i = 0; i < 3; i++)
            {
                esp->k_displacement[3 * m + k] =
                    esp->k_displacement[3 * m + k] +
                    I * (*inv)[m][esp->index_map[i][k]] *
                        esp->k_rhs_homo[3 * m + i];
            }
        }
    }
    // ZF_LOGI("homo disp k %f+%f*i", creal(esp->k_displacement[100]),
    //         cimag(esp->k_displacement[100]));
    // ZF_LOGI("homo rhs k %f+%f*i", creal(esp->k_rhs_homo[100]),
    //         cimag(esp->k_rhs_homo[100]));
}

void n_fft_elastic_solve_homo_rspace(NElasticSolverPtr esp)
{
    if (esp->control_print == 1)
    {
        ZF_LOGI("---------- Homo Elastic Solver for %s Begin ----------",
                esp->solver_name);
    }
    if (esp->control_print_csv == 1)
    {
        n_fft_elastic_print_csv(esp);
    }
    n_fft_elastic_forward(esp);
    n_fft_elastic_rhs_homo_kspace(esp);
    n_fft_elastic_solve_homo_kspace(esp);
    n_fft_elastic_calculate_strain_heterogeneous(esp);
    n_fft_elastic_solver_homo_bc_apply(esp);
    n_fft_elastic_calculate_strain_total(esp);
    n_fft_elastic_backward(esp);
    esp->iteration_index = 0;
    if (esp->control_print == 1)
    {
        ZF_LOGI("----------- Homo Elastic Solver for %s End -----------",
                esp->solver_name);
    }
}

// this will get the strain_avg
void n_fft_elastic_solver_homo_bc_apply(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t j = 0;
    size_t m = 0;
    double eigen_avg[3][3] = {0};
    if (esp->control_constrain_type == 1)
    {
        // this is the stress type need to calculate the strain_avg
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                for (m = 0; m < esp->rspace_totalsize; m++)
                {
                    eigen_avg[i][j] =
                        eigen_avg[i][j] +
                        esp->strain_eigen[6 * m + esp->index_map[i][j]];
                }
            }
        } // for the strain type, need to do nothing
        n_tensor3333_mult_tensor33(esp->strain_avg, esp->compliance_homo,
                                   esp->stress_avg);
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                esp->strain_avg[i][j] = esp->strain_avg[i][j] + eigen_avg[i][j];
            }
        }
    }
}