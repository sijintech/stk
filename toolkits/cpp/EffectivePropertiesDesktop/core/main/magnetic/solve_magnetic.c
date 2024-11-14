#include <effprop/effprop.h>

void pre_solve_distribution_magnetic()
{
    n_fft_poisson_string_set(mps,"poisson_3d/solver_name","magnetic_solve_distribution");
}

void post_solve_magnetic()
{
    memset(magnetic_rhs, 0, sizeof(double) * mps->rspace_totalsize);
}

void solve_distribution_magnetic()
{
    n_fft_poisson_solve_inhomo_rspace(mps);
    calculate_magnetic_induction();
}

void solve_effective_property_magnetic()
{
    size_t i=0;
    size_t j=0;

    int phaseIndex = 0;
    char solvername[128]="";
    char direction[3][5]={"x","y","z"};
    // solve for the effective property
    // apply field along three directions and solve three times.
    for (i = 0; i < 3; i++)
    {
        ZF_LOGI("Apply magnetic field along %zu", i + 1);
        n_fft_poisson_reset(mps);

        external_magnetic_field[0] = 0;
        external_magnetic_field[1] = 0;
        external_magnetic_field[2] = 0;
        external_magnetic_field[i] = 0.001;

        n_fft_poisson_double_array_set(mps, "poisson_3d/external_field", external_magnetic_field);
        n_string_join(solvername, "magnetic_solve_field", direction[i], "_");
        n_fft_poisson_string_set(mps,"poisson_3d/solver_name",solvername);

        solve_distribution_magnetic();

        for (j = 0; j < 3; j++)
        {
            permeability_effective[j][i] = magnetic_induction_avg[j] / external_magnetic_field[i];
            if (fabs(permeability_effective[j][i]) < 1e-16)
            {
                permeability_effective[j][i] = 0;
            }
        }
    }
}