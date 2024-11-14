#include "nmathfft/fft.h"
#include "nmathbasic/nmathbasic.h"

// r2c_3d
// These are exposed to the user
// int r2c_3d_nx, r2c_3d_ny, r2c_3d_nz;
// double r2c_3d_dx, r2c_3d_dy, r2c_3d_dz;
// int r2c_3d_nkx, r2c_3d_nky, r2c_3d_nkz;
// int r2c_3d_totalsize, r2c_3d_totalksize;
// // double (*r2c_3d_kx)[r2c_3d_nkx], (*r2c_3d_ky)[r2c_3d_nky], (*r2c_3d_kz)[r2c_3d_nkz];
// // double *r2c_3d_kx, *r2c_3d_ky, *r2c_3d_kz;
// double *r2c_3d_kvec;

// // Below are hidden within the library
// fftw_plan r2c_3d_planFWD, r2c_3d_planBWD;

// // double (*r2c_3d_in)[r2c_3d_nx][r2c_3d_ny][r2c_3d_nz], (*c2r_3d_out)[r2c_3d_nx][r2c_3d_ny][r2c_3d_nz];
// // fftw_complex (*c2r_3d_in)[r2c_3d_nkx][r2c_3d_nky][r2c_3d_nkz], (*r2c_3d_out)[r2c_3d_nkx][r2c_3d_nky][r2c_3d_nkz];
// double *r2c_3d_in, *c2r_3d_out;
// fftw_complex *c2r_3d_in, *r2c_3d_out;

void n_fftw_r2c_3d_data_int_array_set(NFFTPtr fftptr, const char *name, int *in)
{
    if (strcmp(name, "size") == 0)
    {
        fftptr->nx = in[0];
        fftptr->ny = in[1];
        fftptr->nz = in[2];
    }
}

void n_fftw_r2c_3d_data_double_array_set(NFFTPtr fftptr, const char *name, double *in)
{
    if (strcmp(name, "delta") == 0)
    {
        fftptr->dx = in[0];
        fftptr->dy = in[1];
        fftptr->dz = in[2];
        // ZF_LOGI("Set the r2c fft delta: %f %f %f", in[0], in[1], in[2]);
    }
}

void n_fftw_r2c_3d_data_int_array_get(NFFTPtr fftptr, const char *name, int *out)
{
    if (strcmp(name, "ksize") == 0)
    {
        out[0] = fftptr->nkx;
        out[1] = fftptr->nky;
        out[2] = fftptr->nkz;
    }
    else if (strcmp(name, "size") == 0)
    {
        out[0] = fftptr->nx;
        out[1] = fftptr->ny;
        out[2] = fftptr->nz;
    }
    else if (strcmp(name, "totalsize") == 0)
    {
        *out = fftptr->totalsize;
        // ZF_LOGI("the totalsize %i",fftptr->totalsize);
    }
    else if (strcmp(name, "totalksize") == 0)
    {
        *out = fftptr->totalksize;
        // ZF_LOGI("the totalksize %i",fftptr->totalksize);
    }
}

// void n_fftw_r2c_3d_data_int_get(NFFTPtr fftptr, const char *name, int *out)
// {

// }

void n_fftw_r2c_3d_data_double_array_link(NFFTPtr fftptr, const char *name, double **out)
{
    if (strcmp(name, "kvector") == 0)
    {
        *out = fftptr->kvec;
        // ZF_LOGD("kvec %p %p %f", fftptr->kvec, *out, (*out)[0]);
    }
}

void n_fftw_r2c_3d_data_double_array_get(NFFTPtr fftptr, const char *name, double *out)
{
    size_t i=0;
    if (strcmp(name, "kvector") == 0)
    {
        for (i = 0; i < fftptr->totalksize * 3; i++)
        {
            out[i] = fftptr->kvec[i];
        }
        // ZF_LOGD("kvec %p %p %f", fftptr->kvec, *out, (*out)[0]);
    }
}

void n_fftw_r2c_3d_setup(NFFTPtr fftptr)
{
    int i=0;
    int j=0;
    int k=0;
    fftptr->nkx = fftptr->nx;
    fftptr->nky = fftptr->ny;
    fftptr->nkz = fftptr->nz / 2 + 1;

    fftptr->totalsize = fftptr->nx * fftptr->ny * fftptr->nz;
    fftptr->totalksize = fftptr->nkx * fftptr->nky * fftptr->nkz;

    // ZF_LOGI("The size %i %i",fftptr->totalsize,fftptr->totalksize );
    // out of place transformation needs a padding layer
    n_data_3D_double_init(fftptr->nx, fftptr->ny, fftptr->nz,(double(**)[fftptr->nx][fftptr->ny][fftptr->nz])&fftptr->rin);
    fftptr->rout = fftptr->rin;
    n_data_4D_double_init(fftptr->nkx, fftptr->nky, fftptr->nkz, 3, (double(**)[fftptr->nkx][fftptr->nky][fftptr->nkz][3])&fftptr->kvec);

    fftptr->cout = fftw_alloc_complex(fftptr->totalksize * sizeof(fftw_complex));
    fftptr->cin = fftptr->cout;

    double tempk = 0.0;
    for (i = 0; i < fftptr->nkx; i++)
    {
        for (j = 0; j < fftptr->nky; j++)
        {
            for (k = 0; k < fftptr->nkz; k++)
            {
                if (i >= ((double)fftptr->nx / 2))
                {
                    tempk = i - fftptr->nx;
                }
                else
                {
                    tempk = i;
                }
                fftptr->kvec[i * fftptr->nkz * fftptr->nky * 3 + j * fftptr->nkz * 3 + k * 3 + 0] = 2 * NPI * tempk / (fftptr->dx * (double)fftptr->nx);

                if (j >= ((double)fftptr->ny / 2))
                {
                    tempk = j - (double)fftptr->ny;
                }
                else
                {
                    tempk = j;
                }
                fftptr->kvec[i * fftptr->nkz * fftptr->nky * 3 + j * fftptr->nkz * 3 + k * 3 + 1] = 2 * NPI * tempk / (fftptr->dy * (double)fftptr->ny);

                if (k >= ((double)fftptr->nz / 2))
                {
                    tempk = k - (double)fftptr->nz;
                }
                else
                {
                    tempk = k;
                }
                fftptr->kvec[i * fftptr->nkz * fftptr->nky * 3 + j * fftptr->nkz * 3 + k * 3 + 2] = 2 * NPI * tempk / (fftptr->dz * (double)fftptr->nz);
            }
        }
    }

    fftptr->planFWD = fftw_plan_dft_r2c_3d(fftptr->nx, fftptr->ny, fftptr->nz, fftptr->rin, fftptr->cout, FFTW_MEASURE);
    fftptr->planBWD = fftw_plan_dft_c2r_3d(fftptr->nx, fftptr->ny, fftptr->nz, fftptr->cin, fftptr->rout, FFTW_MEASURE);
    // ZF_LOGI("fftw r2c 3d setup, successful");
}

void n_fftw_r2c_3d_free(NFFTPtr fftptr)
{
    free(fftptr->rin);
    free(fftptr->kvec);
    fftw_free(fftptr->cout);
    fftw_destroy_plan(fftptr->planBWD);
    fftw_destroy_plan(fftptr->planFWD);
}

void n_fftw_r2c_3d_forward(NFFTPtr fftptr, double *in, fftw_complex *out)
{
    fftw_execute_dft_r2c(fftptr->planFWD, in, out);
}

void n_fftw_r2c_n3d_forward(NFFTPtr fftptr, int n, double *in, fftw_complex *out)
{
    int i=0;
    int j=0;
    for (i = 0; i < n; i++)
    {
        for (j = 0; j < fftptr->totalsize; j++)
        {
            fftptr->rin[j] = in[j * n + i];
        }
        n_fftw_r2c_3d_forward(fftptr, fftptr->rin, fftptr->cout);
        for (j = 0; j < fftptr->totalksize; j++)
        {
            out[j * n + i] = fftptr->cout[j];
        }
    }
}

// important the fftw_execute_dft_c2r will change the input!
void n_fftw_r2c_3d_backward(NFFTPtr fftptr, fftw_complex *in, double *out)
{
    size_t i=0;
    memcpy(fftptr->cin, in, fftptr->totalksize * sizeof(fftw_complex));
    // ZF_LOGI("the pointer %p %f %f %i %i",fftptr->planBWD, creal(in[1]),out[1],fftptr->totalsize,fftptr->totalksize);
    fftw_execute_dft_c2r(fftptr->planBWD, fftptr->cin, out);
    for (i = 0; i < fftptr->totalsize; i++)
    {
        // ZF_LOGI("test %i %f",i,out[i]);
        out[i] = out[i] / fftptr->totalsize;
    }
}

void n_fftw_r2c_n3d_backward(NFFTPtr fftptr, int n, fftw_complex *in, double *out)
{
    int i=0;
    size_t j=0;
    for (i = 0; i < n; i++)
    {
        for (j = 0; j < fftptr->totalksize; j++)
        {
            fftptr->cin[j] = in[j * n + i];
        }
        fftw_execute_dft_c2r(fftptr->planBWD, fftptr->cin, fftptr->rout);
        for (j = 0; j < fftptr->totalsize; j++)
        {
            out[j * n + i] = fftptr->rout[j]/ fftptr->totalsize;
        }
    }
}

void n_fftw_r2c_3d_derivative(NFFTPtr fftptr, const char *name, double *in, double *out)
{
    size_t i=0;
    int axis = 0;
    if (strcmp(name, "x") == 0)
    {
        axis = 0;
    }
    else if (strcmp(name, "y") == 0)
    {
        axis = 1;
    }
    else if (strcmp(name, "z") == 0)
    {
        axis = 2;
    }
    n_fftw_r2c_3d_forward(fftptr, in, fftptr->cout);
    for (i = 0; i < fftptr->totalksize; i++)
    {
        fftptr->cout[i] = I * fftptr->kvec[3 * i + axis] * fftptr->cout[i];
    }
    n_fftw_r2c_3d_backward(fftptr, fftptr->cout, out);
}

void n_fftw_r2c_3d_derivative_kspace(NFFTPtr fftptr, const char *name, fftw_complex *in, fftw_complex *out)
{
    size_t i=0;
    int axis = 0;
    if (strcmp(name, "x") == 0)
    {
        axis = 0;
    }
    else if (strcmp(name, "y") == 0)
    {
        axis = 1;
    }
    else if (strcmp(name, "z") == 0)
    {
        axis = 2;
    }
    for (i = 0; i < fftptr->totalksize; i++)
    {
        out[i] = I * fftptr->kvec[3 * i + axis] * in[i];
    }
}

void n_fftw_r2c_3d_derivative_nth_kspace(NFFTPtr fftptr, const char *name, int rank, int nth, fftw_complex *in, fftw_complex *out)
{
    size_t i=0;
    int axis = 0;
    if (strcmp(name, "x") == 0)
    {
        axis = 0;
    }
    else if (strcmp(name, "y") == 0)
    {
        axis = 1;
    }
    else if (strcmp(name, "z") == 0)
    {
        axis = 2;
    }
    for (i = 0; i < fftptr->totalksize; i++)
    {
        out[i] = I * fftptr->kvec[3 * i + axis] * in[rank*i+nth];
    }
}
