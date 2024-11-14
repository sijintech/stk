#include <effprop/effprop.h>

void calculate_diffusion_molar_flux(){
    int phaseIndex = 0;

    molar_flux_avg[0] = 0;
    molar_flux_avg[1] = 0;
    molar_flux_avg[2] = 0;
    size_t k=0;
    size_t l=0;
    size_t m=0;
    for ( k = 0; k < 3; k++)
    {
        for (m = 0; m < dps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            for (l = 0; l < 3; l++)
            {
                molar_flux[3 * m + k] = diffusivity[phaseIndex*9 + 3*k+l] * concentration_gradient[3 * m + l];
                molar_flux_avg[k] = molar_flux_avg[k] + molar_flux[3 * m + k];
            }
        }
        molar_flux_avg[k] = molar_flux_avg[k] / dps->rspace_totalsize;
    }
}