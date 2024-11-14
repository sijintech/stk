#include <nmathfft/elastic.h>

void n_fft_elastic_forward(NElasticSolverPtr esp)
{
    // double (*strain)[esp->rspace_totalsize][6];
    // //now convert to k space, strain stores the elastic strain
    // strain=esp->strain;
    // for (size_t i = 0; i < esp->rspace_totalsize; i++)
    // {
    //     for (size_t j = 0; j < 3; j++)
    //     {
    //         for (size_t k = j; k < 3; k++)
    //         {
    //             (*strain)[i][esp->index_map[j][k]] =
    //             (*strain)[i][esp->index_map[j][k]] - esp->strain_avg[j][k];
    //         }

    //     }

    // }
}

void n_fft_elastic_backward(NElasticSolverPtr esp) {}

void n_fft_elastic_calculate_strain_heterogeneous(NElasticSolverPtr esp)
{
    char prime[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};
    size_t i = 0;
    size_t j = 0;
    size_t m = 0;

    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            // for (size_t m = 0; m < esp->kspace_totalsize; m++)
            // {
            //     esp->k_tmp[m] = esp->k_displacement[3 * m + i] * (I *
            //     esp->kvec[3 * m + j]);
            // }

            n_fft_r2c_derivative_nth_kspace(&esp->nfft, prime[j], 3, i,
                                            esp->k_displacement, esp->k_tmp);
            // ZF_LOGI("disp k %f+%f*i", creal(esp->k_displacement[100]),
            //         cimag(esp->k_displacement[100]));
            // ZF_LOGI("stra k %f+%f*i", creal(esp->k_tmp[100]),
            //         cimag(esp->k_tmp[100]));
            n_fft_backward(
                &esp->nfft, "r2c_3d", esp->k_tmp,
                esp->tmp); // now tmp k is \tilde{\delta\epsilon_{ij}E_{j}}
            // ZF_LOGI("heter strain %i %i %f", i, j, esp->tmp[100]);
            n_data_double_set_nth_component(
                esp->rspace_totalsize, 6, esp->index_map[i][j],
                NPTR2ARR2D(double, esp->strain_heterogeneous,
                           esp->rspace_totalsize, 6),
                esp->tmp);
            // for (size_t m = 0; m < esp->rspace_totalsize; m++)
            // {
            //     esp->strain_heterogeneous[6 * m + esp->index_map[i][j]] =
            //     esp->tmp[m];
            // }
            if (i != j)
            {
                n_fft_r2c_derivative_nth_kspace(&esp->nfft, prime[i], 3, j,
                                                esp->k_displacement,
                                                esp->k_tmp);
                n_fft_backward(
                    &esp->nfft, "r2c_3d", esp->k_tmp,
                    esp->tmp); // now tmp k is \tilde{\delta\epsilon_{ij}E_{j}}
                for (m = 0; m < esp->rspace_totalsize; m++)
                {
                    esp->strain_heterogeneous[6 * m + esp->index_map[i][j]] =
                        0.5 * (esp->strain_heterogeneous[6 * m +
                                                         esp->index_map[i][j]] +
                               esp->tmp[m]);
                }
            }
        }
    }
}

void n_fft_elastic_calculate_displacement(NElasticSolverPtr esp)
{
    size_t i = 0;
    for (i = 0; i < 3; i++)
    {
        n_data_complex_get_nth_component(
            esp->kspace_totalsize, 3, 0, esp->k_tmp,
            NPTR2ARR2D(fftw_complex, esp->k_displacement, esp->kspace_totalsize,
                       3));
        n_fft_backward(
            &esp->nfft, "r2c_3d", esp->k_tmp,
            esp->tmp); // now tmp k is \tilde{\delta\epsilon_{ij}E_{j}}
        n_data_double_set_nth_component(
            esp->rspace_totalsize, 3, 0,
            NPTR2ARR2D(double, esp->displacement, esp->rspace_totalsize, 3),
            esp->tmp);
    }
}

void n_fft_elastic_calculate_strain_total(NElasticSolverPtr esp)
{
    size_t i = 0;
    size_t j = 0;
    size_t m = 0;
    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            for (m = 0; m < esp->rspace_totalsize; m++)
            {
                esp->strain[6 * m + esp->index_map[i][j]] =
                    esp->strain_heterogeneous[6 * m + esp->index_map[i][j]] +
                    esp->strain_avg[i][j];
            }
        }
    }
}

void n_fft_elastic_calculate_stress(NElasticSolverPtr esp)
{
    double(*stiffness)[esp->phase_count][3][3][3][3];
    stiffness =
        &NPTR2ARR5D(double, esp->stiffness, esp->phase_count, 3, 3, 3, 3);
    int phase = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;

    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            for (m = 0; m < esp->rspace_totalsize; m++)
            {
                esp->stress[6 * m + esp->index_map[i][j]] = 0;
                for (k = 0; k < 3; k++)
                {
                    for (l = 0; l < 3; l++)
                    {
                        phase = esp->phase[m];
                        esp->stress[6 * m + esp->index_map[i][j]] =
                            esp->stress[6 * m + esp->index_map[i][j]] +
                            (*stiffness)[phase][i][j][k][l] *
                                (esp->strain[6 * m + esp->index_map[k][l]] -
                                 esp->strain_eigen[6 * m +
                                                   esp->index_map[k][l]]);
                    }
                }
            }
        }
    }
}