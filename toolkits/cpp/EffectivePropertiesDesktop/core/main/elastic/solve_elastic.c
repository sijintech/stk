#include <effprop/effprop.h>

void pre_solve_distribution_elastic()
{
    n_fft_elastic_string_set(ems, "elastic_3d/solver_name",
                             "elastic_solve_distribution");
}

void post_solve_elastic() {}

void solve_distribution_elastic()
{
    // n_fft_elastic_int_set(ems, "elastic_3d/control/max_iterations", 1000); //
    // 0 is the strain constraint
    n_fft_elastic_solve_inhomo_rspace(ems);
    calculate_elastic_stress_strain_avg();
}

void solve_effective_property_elastic()
{
    size_t j = 0;
    size_t i = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;
    size_t n = 0;

    char filename[MAX_STRING] = {0};
    // double stressAvg[3][3] = {0};
    int phaseIndex = 0;
    char solvername[128] = "";
    char direction[6][5] = {"11", "22", "33", "23", "13", "12"};
    // solve for the effective property
    // apply field along three directions and solve three times.
    strcpy(external_elastic_type, "strain");
    n_fft_elastic_int_set(ems, "elastic_3d/control/constrain_type",
                          0); // 0 is the strain constraint
    for (i = 0; i < 3; i++)
    {
        for (j = i; j < 3; j++)
        {

            ZF_LOGI("Apply strain along %zu %zu", i + 1, j + 1);
            n_fft_elastic_reset(ems);
            for (m = 0; m < 3; m++)
            {
                for (n = 0; n < 3; n++)
                {
                    external_strain[m][n] = 0;
                }
            }

            external_strain[i][j] = 0.001;
            external_strain[j][i] = 0.001;

            n_fft_elastic_double_array_set(ems, "elastic_3d/strain_avg",
                                           NARR2PTR(double, external_strain));
            n_string_join(solvername, "elastic_solve_strain",
                          direction[ems->index_map[i][j]], "_");
            n_fft_elastic_string_set(ems, "elastic_3d/solver_name", solvername);

            solve_distribution_elastic();
            sprintf(filename, "out_stress_average_strain%zu%zu=0.001.csv",
                    i + 1, j + 1);
            n_tensor_rank2_print_file(filename, NARR2PTR(double, stress_avg));

            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    if (i == j)
                    {
                        stiffness_effective[k][l][i][j] =
                            stress_avg[k][l] / external_strain[i][j];
                    }
                    else
                    {
                        stiffness_effective[k][l][i][j] =
                            stress_avg[k][l] / external_strain[i][j] / 2;
                    }
                    if (fabs(stiffness_effective[k][l][i][j]) < 1e-8)
                    {
                        stiffness_effective[k][l][i][j] = 0;
                    }
                }
            }
        }
    }

    for (i = 1; i < 3; i++)
    {
        for (j = 0; j < i; j++)
        {
            for (k = 0; k < 3; k++)
            {
                for (l = 0; l < 3; l++)
                {
                    stiffness_effective[k][l][i][j] =
                        stiffness_effective[k][l][j][i];
                }
            }
        }
    }
}