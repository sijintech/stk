#include <effprop/effprop.h>

void pre_solve_distribution_thermal()
{
    n_fft_poisson_string_set(tps,"poisson_3d/solver_name","thermal_solve_distribution");
}

void post_solve_thermal()
{
}

void solve_distribution_thermal()
{

    n_fft_poisson_solve_inhomo_rspace(tps);
    calculate_thermal_heat_flux();
}

void solve_effective_property_thermal(){
    size_t i=0;
    size_t j=0;

    int phaseIndex = 0;
    char solvername[128]="";
    char direction[3][5]={"x","y","z"};

    // solve for the effective property
    // apply field along three directions and solve three times.
    for (i = 0; i < 3; i++)
    {
        ZF_LOGI("Apply concentration gradient along %zu",i+1);
        n_fft_poisson_reset(tps);

        external_temperature_gradient[0] = 0;
        external_temperature_gradient[1] = 0;
        external_temperature_gradient[2] = 0;
        external_temperature_gradient[i] = 0.001;

        n_fft_poisson_double_array_set(tps, "poisson_3d/external_field", external_temperature_gradient);
        n_string_join(solvername, "thermal_solve_field", direction[i], "_");
        n_fft_poisson_string_set(tps,"poisson_3d/solver_name",solvername);

        solve_distribution_thermal();

        for (j = 0; j < 3; j++)
        {
            thermal_conductivity_effective[j][i] = heat_flux_avg[j] / external_temperature_gradient[i] ;
            if (fabs(thermal_conductivity_effective[j][i])<1e-16)
            {
                thermal_conductivity_effective[j][i]=0;
            }
            
        }
    }
}