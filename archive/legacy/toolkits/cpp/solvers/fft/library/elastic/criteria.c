#include "nmathfft/elastic.h"

int n_fft_elastic_check_ready(NElasticSolverPtr esp) { return 1; }

void n_fft_elastic_calculate_energy(NElasticSolverPtr esp)
{
    int index = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;

    for (i = 0; i < esp->rspace_totalsize; i++)
    {
        esp->energy[i] = 0;
        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                index = 6 * i + esp->index_map[j][k];
                esp->energy[i] =
                    esp->energy[i] +
                    esp->stress[index] *
                        (esp->strain[index] - esp->strain_eigen[index]);
            }
        }
    }
    // ZF_LOGI("The stress strain, %f %f",
    //         esp->stress[6 * 100 + esp->index_map[1][1]],
    //         esp->strain[6 * 100 + esp->index_map[1][1]]);
}

double n_fft_elastic_calculate_error(NElasticSolverPtr esp)
{
    // for (size_t i = 0; i < esp->rspace_totalsize; i++)
    // {
    //     esp->tmp[i] = n_vector3_norm(esp->displacement[3*i]);
    // }

    esp->error = 0;
    // double temp=0;
    double hold = 0;
    size_t i = 0;
    for (i = 1; i < esp->rspace_totalsize; i++)
    {
        hold = hold + esp->energy[i];
    }
    esp->error = fabs(esp->total_energy - hold) / fabs(esp->total_energy);
    esp->total_energy = hold;
    if (fabs(hold) < 1e-16)
    {
        esp->error = 0;
    }
    return esp->error;
}

int n_fft_elastic_converge(NElasticSolverPtr esp)
{
    if (esp->error < esp->threshold)
    {
        ZF_LOGI("Converged, error: %13.6le, threshold: %13.6le", esp->error, esp->threshold);
        return 1;
    }
    else
    {
        return 0;
    }
}