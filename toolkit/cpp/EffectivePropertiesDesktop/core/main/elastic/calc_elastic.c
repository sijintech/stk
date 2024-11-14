#include <effprop/effprop.h>

void calculate_elastic_stress_strain_avg()
{
    size_t k=0;
    size_t l=0;
    size_t m=0;
    size_t n=0;
    memcpy(stress_avg_prev, stress_avg, sizeof(double) * 9);
    memcpy(strain_avg_prev, strain_avg, sizeof(double) * 9);
    for (m = 0; m < 3; m++)
    {
        for (n = 0; n < 3; n++)
        {
            stress_avg[m][n] = 0;
            strain_avg[m][n] = 0;
        }
    }

    for (k = 0; k < 3; k++)
    {
        for (l = 0; l < 3; l++)
        {
            for (m = 0; m < ems->rspace_totalsize; m++)
            {

                stress_avg[k][l] = stress_avg[k][l] + stress[6 * m + ems->index_map[k][l]];
                strain_avg[k][l] = strain_avg[k][l] + strain[6 * m + ems->index_map[k][l]];
            }
            stress_avg[k][l] = stress_avg[k][l] / ems->rspace_totalsize;
            strain_avg[k][l] = strain_avg[k][l] / ems->rspace_totalsize;
        }
    }
}

int calculate_elastic_convergence()
{
    size_t i=0;
    size_t j=0;
    double err=0;
    if (strcmp(external_elastic_type, "strain") == 0)
    {
        // compare stress avg
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                if (fabs(stress_avg[i][j]* iter_error) < fabs(stress_avg[i][j] - stress_avg_prev[i][j]) && fabs(stress_avg[i][j]+stress_avg_prev[i][j])>1e-8){
                    ZF_LOGI("Elastic not converged");
                    return 0;
                }
            }
        }
    }
    else
    {
        // compare strain avg
        for (i = 0; i < 3; i++)
        {
            for (j = 0; j < 3; j++)
            {
                if (fabs(strain_avg[i][j]* iter_error) < fabs(strain_avg[i][j] - strain_avg_prev[i][j]) && fabs(strain_avg[i][j]+strain_avg_prev[i][j])>1e-8){
                    ZF_LOGI("Elastic not converged");
                    return 0;
                }
            }
        }
    }
    ZF_LOGI("Elastic converged");
    return 1;
}

void calculate_elastic_eigenstrain_reset()
{
    memset(eigenstrain, 0, sizeof(double) * ems->rspace_totalsize * 6);
    // for (size_t i = 0; i < 3; i++)
    // {
    //     for (size_t j = 0; j < 3; j++)
    //     {
    //         for (size_t m = 0; m < ems->rspace_totalsize; m++)
    //         {
    //             eigenstrain[6 * m + ems->index_map[i][j]] = 0;
    //         }
    //     }
    // }
}

void calculate_elastic_eigenstrain_add_piezoelectric()
{
    size_t i=0;
    size_t j=0;
    size_t k=0;
    size_t m=0;
    // prepare the eigen strain for elastic
    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            for (m = 0; m < ems->rspace_totalsize; m++)
            {
                for (k = 0; k < 3; k++)
                {
                    eigenstrain[6 * m + ems->index_map[i][j]] = eigenstrain[6 * m + ems->index_map[i][j]] + piezoelectric[27 * phase[m] + 9 * k + 3 * i + j] * electric_field[3 * m + k];
                    // if(i!=j){
                    //     eigenstrain[6 * m + ems->index_map[i][j]] = eigenstrain[6 * m + ems->index_map[i][j]]+piezoelectric[27 * phase[m] + 9 * k + 3 * j + i] * electric_field[3 * m + k];
                    // }
                }
            }
        }
    }
}

void calculate_elastic_eigenstrain_add_piezomagnetic()
{
    size_t i=0;
    size_t j=0;
    size_t k=0;
    size_t m=0;
    // prepare the eigen strain for elastic
    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {
            for (m = 0; m < ems->rspace_totalsize; m++)
            {
                for (k = 0; k < 3; k++)
                {
                    eigenstrain[6 * m + ems->index_map[i][j]] = eigenstrain[6 * m + ems->index_map[i][j]] + piezomagnetic[27 * phase[m] + 9 * k + 3 * i + j] * magnetic_field[3 * m + k];
                }
            }
        }
    }
}
