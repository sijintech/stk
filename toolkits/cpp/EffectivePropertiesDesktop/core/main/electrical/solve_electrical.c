#include <effprop/effprop.h>

void pre_solve_distribution_electrical()
{
    n_fft_poisson_string_set(cps,"poisson_3d/solver_name","electrical_solve_distribution");
}

void post_solve_electrical()
{
}

void solve_distribution_electrical()
{
    int phaseIndex = 0;
    n_fft_poisson_solve_inhomo_rspace(cps);
    calculate_electrical_current();
}

void solve_effective_property_electrical()
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
        ZF_LOGI("Apply electric field along %zu",i+1);
        n_fft_poisson_reset(cps);

        external_electric_field[0] = 0;
        external_electric_field[1] = 0;
        external_electric_field[2] = 0;
        external_electric_field[i] = 0.001;

        n_fft_poisson_double_array_set(cps, "poisson_3d/external_field", external_electric_field);
        n_string_join(solvername, "electrical_solve_field", direction[i], "_");
        n_fft_poisson_string_set(cps,"poisson_3d/solver_name",solvername);

        solve_distribution_electrical();

        for (j = 0; j < 3; j++)
        {
            electrical_conductivity_effective[j][i] = electrical_current_avg[j] / external_electric_field[i] ;
            if (fabs(electrical_conductivity_effective[j][i])<1e-16)
            {
                electrical_conductivity_effective[j][i]=0;
            }
        }
    }
}
