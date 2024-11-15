#include <effprop/effprop.h>

void pre_solve_distribution_diffusion()
{
    n_fft_poisson_string_set(dps,"poisson_3d/solver_name","diffusion_solve_distribution");
}

void post_solve_diffusion()
{
}

void solve_distribution_diffusion()
{
    n_fft_poisson_solve_inhomo_rspace(dps);
    calculate_diffusion_molar_flux();

}

void solve_effective_property_diffusion(){
    // double fluxAvg[3] = {0};
    int phaseIndex = 0;
    char solvername[128]="";
    char direction[3][5]={"x","y","z"};
    size_t i=0;
    size_t j=0;

    // solve for the effective property
    // apply field along three directions and solve three times.
    for (i = 0; i < 3; i++)
    {
        ZF_LOGI("Apply concentration gradient along %zu",i+1);
        n_fft_poisson_reset(dps);

        external_concentration_gradient[0] = 0;
        external_concentration_gradient[1] = 0;
        external_concentration_gradient[2] = 0;
        external_concentration_gradient[i] = 0.001;

        n_fft_poisson_double_array_set(dps, "poisson_3d/external_field", external_concentration_gradient);
        n_string_join(solvername, "diffusion_solve_field", direction[i], "_");
        n_fft_poisson_string_set(dps,"poisson_3d/solver_name",solvername);

        solve_distribution_diffusion();

        for (j = 0; j < 3; j++)
        {
            diffusivity_effective[j][i] = molar_flux_avg[j] / external_concentration_gradient[i] ;
            if (fabs(diffusivity_effective[j][i])<1e-16)
            {
                diffusivity_effective[j][i]=0;
            }
            
        }
    }
}