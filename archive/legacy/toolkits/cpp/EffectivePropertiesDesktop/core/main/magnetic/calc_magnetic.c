#include <effprop/effprop.h>

void calculate_magnetic_induction()
{
    size_t m=0;
    size_t k=0;
    size_t l=0;

    memcpy(magnetic_induction_avg_prev, magnetic_induction_avg, sizeof(double) * 3);

    int phaseIndex = 0;
    magnetic_induction_avg[0] = 0;
    magnetic_induction_avg[1] = 0;
    magnetic_induction_avg[2] = 0;
    for (k = 0; k < 3; k++)
    {
        for (m = 0; m < mps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            for (l = 0; l < 3; l++)
            {
                magnetic_induction[3 * m + k] = permeability[phaseIndex * 9 + 3 * k + l] * magnetic_field[3 * m + l];
                magnetic_induction_avg[k] = magnetic_induction_avg[k] + magnetic_induction[3 * m + k];
            }
        }
        magnetic_induction_avg[k] = magnetic_induction_avg[k] / mps->rspace_totalsize;
    }
}

int calculate_magnetic_convergence()
{
    size_t i=0;

    // memcpy(magnetic_induction_avg_prev, magnetic_induction_avg, sizeof(double) * 3);
    double err=0;

    // compare stress avg
    for (i = 0; i < 3; i++)
    {
        err = fabs(magnetic_induction_avg[i] - magnetic_induction_avg_prev[i]);
        if (fabs(magnetic_induction_avg[i] * iter_error) <  err && err > 1e-8)
        {
            ZF_LOGI("Magnetic not converged yet %f",err);
            return 0;
        }
    }
    ZF_LOGI("Magnetic converged");
    return 1;
}

void calculate_magnetic_rhs_reset()
{
    size_t i=0;

    for (i = 0; i < mps->rspace_totalsize; i++)
    {
        magnetic_rhs[i] = 0;
    }
}

void calculate_magnetic_rhs_add_piezomagnetic()
{
    size_t m=0;
    size_t i=0;
    size_t j=0;
    size_t k=0;

    const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};
    int phaseIndex = 0;

    // prepare the spontaneous p and rhs for poisson
    for (i = 0; i < 3; i++)
    {
        memset(tmp,0,sizeof(double)*mps->rspace_totalsize);
        for (m = 0; m < mps->rspace_totalsize; m++)
        {
            for (j = 0; j < 3; j++)
            {
                for (k = 0; k < 3; k++)
                {
                    tmp[m] = tmp[m] + piezomagnetic[27 * phase[m] + 9 * i + 3 * j + k] * stress[6 * m + ems->index_map[j][k]];
                }
            }
        }
        n_fft_r2c_derivative(nfft, derivative_name[i], tmp, tmp1);

        for (m = 0; m < mps->rspace_totalsize; m++)
        {
            magnetic_rhs[m] = magnetic_rhs[m] - tmp1[i];
        }
    }
}

void calculate_magnetic_rhs_add_magnetoelectric()
{
    size_t m=0;
    size_t i=0;
    size_t j=0;

    const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};

    for (i = 0; i < 3; i++)
    {
        for (m = 0; m < mps->rspace_totalsize; m++)
        {
            for (j = 0; j < 3; j++)
            {

                tmp[m] = tmp[m] + magnetoelectric[9 * phase[m] + i + 3 * j] * electric_field[3 * m + j];
            }
        }
        n_fft_r2c_derivative(nfft, derivative_name[i], tmp, tmp1);

        for (m = 0; m < mps->rspace_totalsize; m++)
        {
            magnetic_rhs[m] = magnetic_rhs[m] - tmp1[m];
        }
    }
}