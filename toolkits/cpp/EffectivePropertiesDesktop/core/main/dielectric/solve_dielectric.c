#include <effprop/effprop.h>

void pre_solve_distribution_dielectric()
{
    n_fft_poisson_string_set(eps,"poisson_3d/solver_name","dielectric_solve_distribution");
}

void post_solve_dielectric()
{
}

void solve_distribution_dielectric()
{
    // solve for the distribution
    n_fft_poisson_solve_inhomo_rspace(eps);
    calculate_dielectric_displacement();
    calculate_dielectric_polarization();
}

void solve_effective_property_dielectric()
{
    size_t i=0;
    size_t j=0;
    // double dispAvg[3] = {0};
    int phaseIndex = 0;
    char solvername[128]="";
    char direction[3][5]={"x","y","z"};
    // solve for the effective property
    // apply field along three directions and solve three times.
    for (i = 0; i < 3; i++)
    {
        ZF_LOGI("Apply electric field along %zu", i + 1);
        n_fft_poisson_reset(eps);

        external_electric_field[0] = 0;
        external_electric_field[1] = 0;
        external_electric_field[2] = 0;
        external_electric_field[i] = 0.001;

        n_fft_poisson_double_array_set(eps, "poisson_3d/external_field", external_electric_field);
        n_string_join(solvername, "dielectric_solve_field", direction[i], "_");
        n_fft_poisson_string_set(eps,"poisson_3d/solver_name",solvername);
        // calculate_dielectric_rhs_reset();
        solve_distribution_dielectric();

        for (j = 0; j < 3; j++)
        {
            permittivity_effective[j][i] = electric_displacement_avg[j] / external_electric_field[i];
            if (fabs(permittivity_effective[j][i]) < 1e-16)
            {
                permittivity_effective[j][i] = 0;
            }
        }
    }
}
