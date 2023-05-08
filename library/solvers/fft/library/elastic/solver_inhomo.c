#include "nmathfft/elastic.h"

void n_fft_elastic_rhs_inhomo_kspace(NElasticSolverPtr esp)
{
    size_t m = 0;
    n_fft_elastic_rhs_homo_kspace(esp);
    for (m = 0; m < 3 * esp->kspace_totalsize; m++)
    {
        esp->k_rhs_inhomo[m] = esp->k_rhs_homo[m];
    }
    // ZF_LOGI("inhomo rhs kspace %f+%fi", creal(esp->k_rhs_inhomo[100]),
    //         cimag(esp->k_rhs_inhomo[100]));
}

void n_fft_elastic_rhs_iterate_kspace(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;
    int phase = 0;
    double(*delta)[esp->phase_count][3][3][3][3];
    double(*strain)[esp->rspace_totalsize][6];
    double(*eigen)[esp->rspace_totalsize][6];
    double(*stiff)[esp->phase_count][3][3][3][3];

    fftw_complex(*k_rhs)[esp->kspace_totalsize][3];
    delta =
        &NPTR2ARR5D(double, esp->stiffness_delta, esp->phase_count, 3, 3, 3, 3);
    strain = &NPTR2ARR2D(double, esp->strain, esp->rspace_totalsize, 6);
    eigen = &NPTR2ARR2D(double, esp->strain_eigen, esp->rspace_totalsize, 6);
    stiff = &NPTR2ARR5D(double, esp->stiffness, esp->phase_count, 3, 3, 3, 3);

    // ZF_LOGI("before infor");
    // ZF_LOGI("stiff %i %f %f", esp->phase[100], (*stiff)[0][1][1][1][1],
    //         (*stiff)[0][1][1][2][2]);
    // ZF_LOGI("stiffness %i %f %f", esp->phase[100], esp->stiffness[0],
    //         esp->stiffness[4]);

    k_rhs =
        &NPTR2ARR2D(fftw_complex, esp->k_rhs_homo, esp->kspace_totalsize, 3);
    int index = 0;
    memset(esp->k_rhs_homo, 0,
           sizeof(fftw_complex) * esp->kspace_totalsize * 3);
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            memset(esp->tmp, 0, sizeof(double) * esp->rspace_totalsize);
            for (m = 0; m < esp->rspace_totalsize; m++)
            {
                phase = esp->phase[m];
                for (k = 0; k < 3; k++)
                {
                    for (l = 0; l < 3; l++)
                    {
                        // esp->tmp[m] = esp->tmp[m] +
                        // (*delta)[phase][i][j][k][l] *
                        // ((*strain)[m][esp->index_map[k][l]]-(*eigen)[m][esp->index_map[k][l]]);
                        esp->tmp[m] =
                            esp->tmp[m] + ((*delta)[phase][i][j][k][l] *
                                           (*strain)[m][esp->index_map[k][l]]);
                    }
                }
                // if (fabs(esp->tmp[m]) > 1)
                // {
                //     ZF_LOGI("in tmp %i %f", m, esp->tmp[m]);
                //     ZF_LOGI("in strain %i %f %f %f %f %f %f", m,
                //             (*strain)[m][0], (*strain)[m][1],
                //             (*strain)[m][2],
                //             (*strain)[m][3], (*strain)[m][4],
                //             (*strain)[m][5]);
                //     ZF_LOGI("delta %i %f %f", esp->phase[m],
                //             (*delta)[phase][1][1][1][1],
                //             (*delta)[phase][1][1][2][2]);
                //     ZF_LOGI("stiff0 %i %f %f", esp->phase[m],
                //             (*stiff)[0][1][1][1][1],
                //             (*stiff)[0][1][1][2][2]);
                //     ZF_LOGI("stiff1 %i %f %f", esp->phase[m],
                //             (*stiff)[1][1][1][1][1],
                //             (*stiff)[1][1][1][2][2]);
                //     ZF_LOGI("homo %f %f", esp->stiffness_homo[1][1][1][1],
                //             esp->stiffness_homo[1][1][2][2]);
                //     // ZF_LOGI("stiff %i %f %f", esp->phase[100],
                //     //         (*stiff)[0][1][1][1][1],
                //     //         (*stiff)[0][1][1][2][2]);
                // }
            }
            n_fft_forward(&esp->nfft, "r2c_3d", esp->tmp,
                          esp->k_tmp); // now tmp k is
                                       // \tilde{\delta\epsilon_{ij}E_{j}}
            // ZF_LOGI("inside %i %i %f %f", i, j, esp->tmp[0], esp->tmp[100]);
            // ZF_LOGI("insid k_tmp %i %i %f+%fi", i, j, creal(esp->k_tmp[100]),
            //         cimag(esp->k_tmp[100]));
            // exit(0);
            for (m = 0; m < esp->kspace_totalsize; m++)
            {
                (*k_rhs)[m][i] =
                    (*k_rhs)[m][i] + esp->k_tmp[m] * esp->kvec[3 * m + j];
            }
        }

        for (m = 0; m < esp->kspace_totalsize; m++)
        {
            (*k_rhs)[m][i] = (*k_rhs)[m][i] + esp->k_rhs_inhomo[3 * m + i];
        }
        // ZF_LOGI("rhs homo after inhomo k %f+%f*i",
        // creal(esp->k_rhs_homo[100]),
        //         cimag(esp->k_rhs_homo[100]));
        // ZF_LOGI("inhomo rhs kspace %f+%fi", creal(esp->k_rhs_inhomo[100]),
        //         cimag(esp->k_rhs_inhomo[100]));
    }
}

void n_fft_elastic_solve_inhomo_kspace(NElasticSolverPtr esp)
{
    size_t i = 0;
    for (i = 0; i < esp->max_iterations; i++)
    {
        n_fft_elastic_rhs_iterate_kspace(esp);
        n_fft_elastic_solve_homo_kspace(esp);
        n_fft_elastic_calculate_strain_heterogeneous(esp);
        n_fft_elastic_calculate_strain_total(esp);
        n_fft_elastic_solver_inhomo_bc_apply(esp);
        n_fft_elastic_calculate_stress(esp);
        // memcpy(esp->tmp,esp->energy,esp->rspace_totalsize*sizeof(double));
        n_fft_elastic_calculate_energy(esp);
        esp->iteration_index = esp->iteration_index + 1;
        n_fft_elastic_calculate_error(esp);
        // need to print some information
        if (esp->control_print == 1)
            n_fft_elastic_print_screen(esp);
        if (esp->control_print_csv == 1)
            n_fft_elastic_print_csv(esp);
        if (n_fft_elastic_converge(esp) == 1 && i > 0)
            break;
    }
}

void n_fft_elastic_solve_inhomo_rspace(NElasticSolverPtr esp)
{
    // need to check the array linking and calloc conditions
    if (n_fft_elastic_check_ready(esp) != 1)
    {
        ZF_LOGE("Something is not ready");
    }

    // need to add some printing utilities
    if (esp->control_print == 1)
    {
        ZF_LOGI("---------- Elastic Inhomo Solver for %s Begin ----------",
                esp->solver_name);
    }
    if (esp->control_print_csv == 1)
    {
        n_fft_elastic_print_csv_header(esp);
    }
    n_fft_elastic_calculate_strain_total(esp);

    // need to first convert the system into kspace
    n_fft_elastic_forward(esp);

    // setup the unchanged part of rhs and solve the equation
    n_fft_elastic_rhs_inhomo_kspace(esp);
    n_fft_elastic_solve_inhomo_kspace(esp);

    // need to convert the kspace back to rsapce
    n_fft_elastic_backward(esp);
    n_fft_elastic_calculate_displacement(esp);
    n_fft_elastic_calculate_stress(esp);
    esp->iteration_index = 0;
    if (esp->control_print == 1)
    {
        ZF_LOGI("---------- Elastic Inhomo Solver for %s End ----------",
                esp->solver_name);
    }
}

// this will get the strain_avg
void n_fft_elastic_solver_inhomo_bc_apply(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t j = 0;
    size_t m = 0;
    double strain_avg[3][3] = {0};
    double stress_avg[3][3] = {0};
    double strain_diff[3][3] = {0};
    double stress_diff[3][3] = {0};
    if (esp->control_constrain_type == 1)
    {
        // this is the stress type need to calculate the strain_avg
        n_fft_elastic_calculate_stress(esp);
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                for (m = 0; m < esp->rspace_totalsize; m++)
                {
                    stress_avg[i][j] =
                        stress_avg[i][j] +
                        esp->stress[6 * m + esp->index_map[i][j]];
                }
                stress_diff[i][j] = esp->stress_avg[i][j] -
                                    stress_avg[i][j] / esp->rspace_totalsize;
            }
        }

        n_tensor3333_mult_tensor33(strain_diff, esp->compliance_homo,
                                   stress_diff);
    }
    else
    { // else is when 0 the strain type
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                for (m = 0; m < esp->rspace_totalsize; m++)
                {
                    strain_avg[i][j] =
                        strain_avg[i][j] +
                        esp->strain[6 * m + esp->index_map[i][j]];
                }
                strain_diff[i][j] = esp->strain_avg[i][j] -
                                    strain_avg[i][j] / esp->rspace_totalsize;
            }
        }
    }

    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            for (m = 0; m < esp->rspace_totalsize; m++)
            {
                esp->strain[6 * m + esp->index_map[i][j]] =
                    strain_diff[i][j] +
                    esp->strain[6 * m + esp->index_map[i][j]];
            }
        }
    }
}