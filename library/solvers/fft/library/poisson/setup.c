#include <fftw/fftw3.h>
#include <nmathfft/poisson.h>

// init should be called only once, as long as the homo part is the same
// the data array linking should happen before the init
void n_fft_poisson_init(NPoissonSolverPtr psp, NFFTPtr nfftptr)
{
    size_t i = 0;
    size_t j = 0;
    psp->control_rhs_source_nonzero = 1;
    // psp->control_epsilon_delta_nonzero = 1;
    psp->control_external_field_nonzero = 1;
    psp->control_auto_index_update = 1;
    psp->control_print = 1;
    psp->control_print_csv = 1;
    psp->solver_index = 0;
    psp->total_energy = 1;
    // psp->phase_count = 1;
    psp->nfft = *nfftptr;
    psp->iter_step = 0.5;

    psp->max_iterations = 1000;
    psp->error = 1;
    psp->threshold = 1e-4;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            psp->epsilon_homo[i][j] = 0;
        }
        psp->external_field[i] = 0;
    }
    strcpy(psp->solver_name, "electric");
    strcpy(psp->csv_filename, "electric.csv");

    psp->iteration_index = 0;
    psp->link_flag_potential = 0;
    psp->link_flag_epsilon = 0;
    psp->link_flag_field = 0;
    psp->link_flag_rhs_source = 0;
    psp->set_flag_epsilon_homo = 0;
    psp->set_flag_external_field = 0;
    if (psp->set_flag_phase_count == 0 && psp->control_solver_homo == 1)
    {
        ZF_LOGE("You must either set poisson_3d/control/solver/homo to 1 or "
                "set the number of phases using poisson_3d/phase_count");
    }

    psp->in_kspace = 0; // 0 means in rsapce, 1 in kspace;

    psp->index_map[0][0] = 0;
    psp->index_map[1][1] = 1;
    psp->index_map[2][2] = 2;
    psp->index_map[1][2] = 3;
    psp->index_map[2][1] = 3;
    psp->index_map[0][2] = 4;
    psp->index_map[2][0] = 4;
    psp->index_map[0][1] = 5;
    psp->index_map[1][0] = 5;

    ZF_LOGI("psp setup");
    n_fft_data_get(nfftptr, "r2c_3d/totalksize", &(psp->kspace_totalsize));
    n_fft_data_get(nfftptr, "r2c_3d/totalsize", &(psp->rspace_totalsize));
    n_fft_data_link(nfftptr, "r2c_3d/kvector", &(psp->kvec));
    psp->tmp = calloc(psp->rspace_totalsize, sizeof(double));
    psp->epsilon_delta = calloc(psp->phase_count * 9, sizeof(double));
    psp->A_inverse = calloc(psp->kspace_totalsize, sizeof(double));
    psp->k_tmp = (fftw_complex*)fftw_malloc(psp->kspace_totalsize *
                                            sizeof(fftw_complex));
    psp->k_rhs_homo = (fftw_complex*)fftw_malloc(psp->kspace_totalsize *
                                                 sizeof(fftw_complex));
    psp->k_rhs_inhomo = (fftw_complex*)fftw_malloc(psp->kspace_totalsize *
                                                   sizeof(fftw_complex));
    psp->k_potential = (fftw_complex*)fftw_malloc(psp->kspace_totalsize *
                                                  sizeof(fftw_complex));
    // psp->poisson_3d_potential = calloc(psp->rspace_totalsize,
    // sizeof(double));

    for (i = 0; i < psp->kspace_totalsize; i++)
    {
        n_fft_assign_zero(&psp->k_tmp[i]);
        n_fft_assign_zero(&psp->k_rhs_homo[i]);
        n_fft_assign_zero(&psp->k_rhs_inhomo[i]);
        n_fft_assign_zero(&psp->k_potential[i]);
        // psp->k_tmp[i] = 0 + 0 * I;
        // psp->k_rhs_homo[i] = 0 + 0 * I;
        // psp->k_rhs_inhomo[i] = 0 + 0 * I;
        // psp->k_potential[i] = 0 + 0 * I;
    }
}

void n_fft_poisson_setup(NPoissonSolverPtr psp)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    double(*delta)[psp->phase_count][3][3];
    delta = &NPTR2ARR3D(double, psp->epsilon_delta, psp->phase_count, 3, 3);
    double(*epsilon)[psp->phase_count][3][3];
    epsilon = &NPTR2ARR3D(double, psp->epsilon, psp->phase_count, 3, 3);
    for (k = 0; k < psp->phase_count; k++)
    {
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                (*delta)[k][i][j] =
                    (*epsilon)[k][i][j] - psp->epsilon_homo[i][j];
            }
        }
    }

    for (k = 0; k < psp->kspace_totalsize; k++)
    {
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                psp->A_inverse[k] =
                    psp->A_inverse[k] + psp->epsilon_homo[i][j] *
                                            psp->kvec[3 * k + i] *
                                            psp->kvec[3 * k + j];
            }
        }
        if (psp->A_inverse[k] < 1e-8)
        {
            psp->A_inverse[k] = 0.0;
        }
        else
        {
            psp->A_inverse[k] = 1.0 / psp->A_inverse[k];
        }
    }
}

void n_fft_poisson_reset(NPoissonSolverPtr psp)
{
    memset(psp->k_tmp, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    memset(psp->k_rhs_homo, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    memset(psp->k_rhs_inhomo, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    memset(psp->k_potential, 0, sizeof(fftw_complex) * psp->kspace_totalsize);
    memset(psp->tmp, 0, sizeof(double) * psp->rspace_totalsize);
    memset(psp->field, 0, 3 * sizeof(double) * psp->rspace_totalsize);
    memset(psp->potential, 0, sizeof(double) * psp->rspace_totalsize);
    psp->total_energy = 1;
    psp->error = 1;
}

void n_fft_poisson_free(NPoissonSolverPtr psp)
{
    free(psp->tmp);
    free(psp->A_inverse);
    free(psp->epsilon_delta);
    fftw_free(psp->k_tmp);
    fftw_free(psp->k_rhs_homo);
    fftw_free(psp->k_rhs_inhomo);
    fftw_free(psp->k_potential);
    // poisson_3d_control_epsilon_delta_nonzero = 1;
    // poisson_3d_control_external_field_nonzero = 1;
    // poisson_3d_control_rhs_source_nonzero = 1;
    // poisson_3d_solver_index=0;
    // poisson_3d_iteration_index=0;
    free(psp);
}
