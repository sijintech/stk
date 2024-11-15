#include "effprop/effprop.h"

void calculate_dielectric_displacement()
{
    // memcpy(electric_displacement_avg_prev, electric_displacement_avg,
    // sizeof(double) * 3);
    memcpy(electric_displacement_avg_prev, electric_displacement_avg,
           sizeof(double) * 3);
    electric_displacement_avg[0] = 0;
    electric_displacement_avg[1] = 0;
    electric_displacement_avg[2] = 0;
    size_t k = 0;
    size_t l = 0;
    size_t m = 0;
    int phaseIndex = 0;
    for (k = 0; k < 3; k++)
    {
        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            for (l = 0; l < 3; l++)
            {
                electric_displacement[3 * m + k] =
                    spontaneous_polarization[3 * m + k] +
                    permittivity[phaseIndex * 9 + 3 * k + l] *
                        electric_field[3 * m + l];
                electric_displacement_avg[k] = electric_displacement_avg[k] +
                                               electric_displacement[3 * m + k];
            }
        }
        electric_displacement_avg[k] =
            electric_displacement_avg[k] / eps->rspace_totalsize;
    }
}

void calculate_dielectric_polarization()
{
    int phaseIndex = 0;
    size_t k = 0;
    size_t m = 0;
    for (k = 0; k < 3; k++)
    {
        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            phaseIndex = phase[m];
            polarization[3 * m + k] = electric_displacement[3 * m + k] -
                                      NEPSILON0 * electric_field[3 * m + k];
        }
    }
}

int calculate_dielectric_convergence()
{
    double err = 0;
    // compare stress avg
    size_t i = 0;
    for (i = 0; i < 3; i++)
    {
        err = fabs(electric_displacement_avg[i] -
                   electric_displacement_avg_prev[i]);
        if (fabs(electric_displacement_avg[i] * iter_error) < err && err > 1e-8)
        {
            ZF_LOGI("Dielectric not converged yet %f", err);
            return 0;
        }
    }
    ZF_LOGI("Dielectric converged");
    return 1;
}

void calculate_dielectric_rhs_reset()
{
    // now prepare the rhs;
    const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};
    // prepare the rhs
    size_t i = 0;
    size_t m = 0;
    for (i = 0; i < eps->rspace_totalsize; i++)
    {
        dielectric_rhs[i] = charge[i] / NEPSILON0;
    }

    for (m = 0; m < 3; m++)
    {
        n_data_double_get_nth_component(eps->rspace_totalsize, 3, m, tmp,
                                        NPTR2ARR2D(double,
                                                   spontaneous_polarization,
                                                   eps->rspace_totalsize, 3));
        n_fft_r2c_derivative(nfft, derivative_name[m], tmp, tmp1);
        for (i = 0; i < eps->rspace_totalsize; i++)
        {
            dielectric_rhs[i] = dielectric_rhs[i] - tmp1[i] / NEPSILON0;
        }
    }
}

void calculate_dielectric_rhs_add_piezoelectric()
{
    const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};
    int phaseIndex = 0;
    size_t i = 0;
    size_t j = 0;
    size_t k = 0;
    size_t m = 0;
    // prepare the spontaneous p and rhs for poisson
    for (i = 0; i < 3; i++)
    {
        memset(tmp, 0, sizeof(double) * eps->rspace_totalsize);
        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            for (j = 0; j < 3; j++)
            {
                for (k = 0; k < 3; k++)
                {
                    tmp[m] = tmp[m] +
                             piezoelectric[27 * phase[m] + 9 * i + 3 * j + k] *
                                 stress[6 * m + ems->index_map[j][k]];
                }
            }
        }
        n_fft_r2c_derivative(nfft, derivative_name[i], tmp, tmp1);

        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            dielectric_rhs[m] = dielectric_rhs[m] - tmp1[m];
        }
    }
}

void calculate_dielectric_rhs_add_magnetoelectric()
{
    const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};

    size_t i = 0;
    size_t j = 0;
    size_t m = 0;
    // prepare the spontaneous p and rhs for poisson
    for (i = 0; i < 3; i++)
    {
        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            for (j = 0; j < 3; j++)
            {
                tmp[m] = tmp[m] + magnetoelectric[9 * phase[m] + 3 * i + j] *
                                      magnetic_field[3 * m + j];
            }
        }
        n_fft_r2c_derivative(nfft, derivative_name[i], tmp, tmp1);

        for (m = 0; m < eps->rspace_totalsize; m++)
        {
            dielectric_rhs[m] = dielectric_rhs[m] - tmp1[m];
        }
    }
}