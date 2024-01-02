#include <nmathbasic/nmathbasic.h>
#include <nmathfft/elastic.h>

void n_fft_elastic_init(NElasticSolverPtr esp, NFFTPtr nfftptr)
{
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    // esp->control_stiffness_delta_nonzero = 1;
    esp->control_constrain_type = 0;
    esp->solver_index = 0;
    esp->total_energy = 1;
    // esp->phase_count = 1;
    esp->max_iterations = 1000;
    esp->nfft = *nfftptr;
    esp->error = 0;
    esp->threshold = 1e-4;
    esp->control_print = 1;
    esp->control_print_csv = 1;
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    esp->stiffness_homo[i][j][k][l] = 0;
                    esp->compliance_homo[i][j][k][l] = 0;
                }
            }
            esp->strain_avg[i][j] = 0;
            esp->stress_avg[i][j] = 0;
        }
    }
    strcpy(esp->solver_name, "elastic");
    strcpy(esp->csv_filename, "elastic.csv");
    esp->iteration_index = 0;
    esp->link_flag_stress = 0;
    esp->link_flag_strain = 0;
    esp->link_flag_displacement = 0;
    esp->set_flag_stiffness_homo = 0;
    esp->set_flag_phase_count = 0;
    esp->set_flag_constrain = 0;

    if (esp->set_flag_phase_count == 0 && esp->control_solver_homo == 1)
    {
        ZF_LOGE("You must either set poisson_3d/control/solver/homo to 1 or "
                "set the number of phases using poisson_3d/phase_count");
    }

    esp->index_map[0][0] = 0;
    esp->index_map[1][1] = 1;
    esp->index_map[2][2] = 2;
    esp->index_map[1][2] = 3;
    esp->index_map[2][1] = 3;
    esp->index_map[0][2] = 4;
    esp->index_map[2][0] = 4;
    esp->index_map[0][1] = 5;
    esp->index_map[1][0] = 5;

    n_fft_data_get(nfftptr, "r2c_3d/totalksize", &(esp->kspace_totalsize));
    n_fft_data_get(nfftptr, "r2c_3d/totalsize", &(esp->rspace_totalsize));
    n_fft_data_link(nfftptr, "r2c_3d/kvector", &(esp->kvec));

    esp->tmp = calloc(esp->rspace_totalsize, sizeof(double));
    esp->stiffness_delta = calloc(esp->phase_count * 81, sizeof(double));
    esp->strain_heterogeneous =
        calloc(esp->rspace_totalsize * 6, sizeof(double));

    esp->A_inverse = calloc(esp->kspace_totalsize * 6, sizeof(double));
    esp->k_tmp = (fftw_complex*)fftw_malloc(esp->kspace_totalsize *
                                            sizeof(fftw_complex));
    esp->k_rhs_homo = (fftw_complex*)fftw_malloc(3 * esp->kspace_totalsize *
                                                 sizeof(fftw_complex));
    esp->k_displacement = (fftw_complex*)fftw_malloc(3 * esp->kspace_totalsize *
                                                     sizeof(fftw_complex));
    esp->k_rhs_inhomo = (fftw_complex*)fftw_malloc(3 * esp->kspace_totalsize *
                                                   sizeof(fftw_complex));

    for (i = 0; i < esp->kspace_totalsize; i++)
    {
        esp->k_tmp[i] = 0 + 0 * I;
        esp->k_displacement[3 * i + 0] = 0 + 0 * I;
        esp->k_displacement[3 * i + 1] = 0 + 0 * I;
        esp->k_displacement[3 * i + 2] = 0 + 0 * I;

        for (j = 0; j < 6; j++)
        {
            esp->k_rhs_homo[i] = 0 + 0 * I;
            esp->k_rhs_inhomo[i] = 0 + 0 * I;
        }
    }
}

void n_fft_elastic_setup(NElasticSolverPtr esp)
{
    double A[3][3] = {0}, A_in[3][3] = {0};
    double(*inv)[esp->kspace_totalsize][6];
    double(*kvec)[esp->kspace_totalsize][3];
    inv = &NPTR2ARR2D(double, esp->A_inverse, esp->kspace_totalsize, 6);
    kvec = &NPTR2ARR2D(double, esp->kvec, esp->kspace_totalsize, 3);
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;

    // set the A_inverse
    for (m = 0; m < esp->kspace_totalsize; m++)
    {
        for (i = 0; i < 3; i++)
        {
            for (k = 0; k < 3; k++)
            {
                A[i][k] = 0;
                for (j = 0; j < 3; j++)
                {
                    for (l = 0; l < 3; l++)
                    {
                        A[i][k] = A[i][k] + esp->stiffness_homo[i][j][k][l] *
                                                (*kvec)[m][l] * (*kvec)[m][j];
                    }
                }
            }
        }

        n_matrix33_inverse(A_in, A);
        for (i = 0; i < 3; i++)
        {
            for (k = i; k < 3; k++)
            {
                (*inv)[m][esp->index_map[i][k]] = A_in[i][k];
            }
        }
    }

    n_tensor3333_inverse66(esp->compliance_homo, esp->stiffness_homo);
    // set up the k_rhs_unchanged
    double(*delta)[esp->phase_count][3][3][3][3];
    double(*stiff)[esp->phase_count][3][3][3][3];
    int phase;
    delta =
        &NPTR2ARR5D(double, esp->stiffness_delta, esp->phase_count, 3, 3, 3, 3);
    stiff = &NPTR2ARR5D(double, esp->stiffness, esp->phase_count, 3, 3, 3, 3);

    for (m = 0; m < esp->phase_count; m++)
    {
        for (i = 0; i < 3; i++)
        {
            for (k = 0; k < 3; k++)
            {
                for (j = 0; j < 3; j++)
                {
                    for (l = 0; l < 3; l++)
                    {
                        (*delta)[m][i][j][k][l] =
                            (*stiff)[m][i][j][k][l] -
                            esp->stiffness_homo[i][j][k][l];
                    }
                }
            }
        }
    }
}

void n_fft_elastic_reset(NElasticSolverPtr esp)
{
    memset(esp->k_tmp, 0, sizeof(fftw_complex) * esp->kspace_totalsize);
    memset(esp->k_rhs_homo, 0, sizeof(fftw_complex) * esp->kspace_totalsize);
    memset(esp->k_rhs_inhomo, 0, sizeof(fftw_complex) * esp->kspace_totalsize);
    memset(esp->k_displacement, 0,
           3 * sizeof(fftw_complex) * esp->kspace_totalsize);
    memset(esp->tmp, 0, sizeof(double) * esp->rspace_totalsize);
    memset(esp->strain_heterogeneous, 0,
           6 * sizeof(double) * esp->rspace_totalsize);
    memset(esp->strain, 0, 6 * sizeof(double) * esp->rspace_totalsize);
    memset(esp->stress, 0, 6 * sizeof(double) * esp->rspace_totalsize);
    memset(esp->displacement, 0, 3 * sizeof(double) * esp->rspace_totalsize);
    esp->total_energy = 1;
    esp->error = 1;
}

void n_fft_elastic_free(NElasticSolverPtr esp)
{
    free(esp->A_inverse);
    free(esp->tmp);
    fftw_free(esp->k_tmp);
    fftw_free(esp->k_rhs_homo);
    fftw_free(esp->k_rhs_inhomo);
}