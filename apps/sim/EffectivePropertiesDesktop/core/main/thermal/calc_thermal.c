#include <effprop/effprop.h>

void calculate_thermal_heat_flux(){

    size_t k=0;
    size_t l=0;
    size_t m=0;
    int phaseIndex = 0;

    heat_flux_avg[0] = 0;
    heat_flux_avg[1] = 0;
    heat_flux_avg[2] = 0;

    for (k = 0; k < 3; k++)
    {
        for (m = 0; m < tps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            for (l = 0; l < 3; l++)
            {
                heat_flux[3 * m + k] = thermal_conductivity[phaseIndex*9 + 3*k+l] * temperature_gradient[3 * m + l];
                heat_flux_avg[k] = heat_flux_avg[k] + heat_flux[3 * m + k];
            }
        }
        heat_flux_avg[k] = heat_flux_avg[k] / tps->rspace_totalsize;
    }
}