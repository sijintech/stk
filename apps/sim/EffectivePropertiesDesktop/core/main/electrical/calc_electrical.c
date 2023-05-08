#include <effprop/effprop.h>

void calculate_electrical_current(){
    size_t k=0;
    size_t l=0;
    size_t m=0;

    int phaseIndex = 0;

    electrical_current_avg[0] = 0;
    electrical_current_avg[1] = 0;
    electrical_current_avg[2] = 0;
    
    for (k = 0; k < 3; k++)
    {
        for (m = 0; m < cps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            for (l = 0; l < 3; l++)
            {
                electrical_current[3 * m + k] = electrical_conductivity[phaseIndex*9 + 3*k+l] * electric_field[3 * m + l];
                electrical_current_avg[k] = electrical_current_avg[k] + electrical_current[3 * m + k];
            }
        }
        electrical_current_avg[k] = electrical_current_avg[k] / cps->rspace_totalsize;
    }
}