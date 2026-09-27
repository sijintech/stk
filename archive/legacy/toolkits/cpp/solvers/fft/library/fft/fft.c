#include <nmathfft/fft.h>
#include <ntextutils/ntextutils.h>

NFFT n_fft;

void n_fft_assign_zero(fftw_complex* x) { memset(x, 0, sizeof(fftw_complex)); }

void n_fft_data_int_array_set_f(const char* name, int** in)
{
    n_fft_data_int_array_set(&n_fft, name, *in);
}
void n_fft_data_int_array_set(NFFTPtr fftptr, const char* name, int* in)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_data_int_array_set(fftptr, text.data, in);
    }
}

void n_fft_data_double_array_set_f(const char* name, double** in)
{
    n_fft_data_double_array_set(&n_fft, name, *in);
}
void n_fft_data_double_array_set(NFFTPtr fftptr, const char* name, double* in)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_data_double_array_set(fftptr, text.data, in);
    }
}

void n_fft_data_int_array_get_f(const char* name, int** out)
{
    n_fft_data_int_array_get(&n_fft, name, *out);
}
void n_fft_data_int_array_get(NFFTPtr fftptr, const char* name, int* out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_data_int_array_get(fftptr, text.data, out);
    }
}
// void n_fft_data_int_get_f(const char *name, int **out)
// {
//     n_fft_data_int_get(&n_fft, name, *out);
// }

// void n_fft_data_int_get(NFFTPtr fftptr,const char *name, int *out)
// {
//     if (n_string_exist(name, "r2c_3d/") == 1)
//     {
//         NString text = n_string_split_rest_by_token(name, "/");
//         n_fftw_r2c_3d_data_int_get(fftptr, text.data, out);
//     }
// }

// void n_fft_data_double_array_link_f(const char *name, double **out)
// {
//     n_fft_data_double_array_link(&n_fft, name, out);
// }
// this can only be used in C, in fortran we can only set the data value, not
// the pointer
void n_fft_data_double_array_link(NFFTPtr fftptr, const char* name,
                                  double** out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        // ZF_LOGE("Using the correct one");
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_data_double_array_link(fftptr, text.data, out);
        // n_fftw_r2c_3d_double_data_get(name, out);
        // ZF_LOGI("kvec %s %p", name, *out);
    }
}

void n_fft_data_double_array_get_f(const char* name, double** out)
{
    n_fft_data_double_array_get(&n_fft, name, *out);
}
void n_fft_data_double_array_get(NFFTPtr fftptr, const char* name, double* out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        // ZF_LOGE("Using the correct one");
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_data_double_array_get(fftptr, text.data, out);
        // n_fftw_r2c_3d_double_data_get(name, out);
        // ZF_LOGI("kvec %s %p", name, *out);
    }
}

void n_fft_r2c_forward_f(const char* name, double** in, fftw_complex** out)
{
    n_fft_r2c_forward(&n_fft, name, *in, *out);
}
void n_fft_r2c_forward(NFFTPtr fftptr, const char* name, double* in,
                       fftw_complex* out)
{
    if (strcmp(name, "r2c_3d") == 0)
    {
        n_fftw_r2c_3d_forward(fftptr, in, out);
    }
    else if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        int n = atoi(text.data);
        // ZF_LOGD("The new r2c forward %s %i",name,n);
        n_fftw_r2c_n3d_forward(fftptr, n, in, out);
    }
}

void n_fft_r2c_backward_f(const char* name, fftw_complex** in, double** out)
{
    n_fft_r2c_backward(&n_fft, name, *in, *out);
}
void n_fft_r2c_backward(NFFTPtr fftptr, const char* name, fftw_complex* in,
                        double* out)
{
    if (strcmp(name, "r2c_3d") == 0)
    {
        n_fftw_r2c_3d_backward(fftptr, in, out);
    }
    else if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        int n = atoi(text.data);
        // ZF_LOGD("The new r2c backward %s %i",name,n);
        n_fftw_r2c_n3d_backward(fftptr, n, in, out);
    }
}

void n_fft_derivative_f(const char* name, double** in, double** out)
{
    n_fft_derivative(&n_fft, name, *in, *out);
}
void n_fft_r2c_derivative(NFFTPtr fftptr, const char* name, double* in,
                          double* out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_derivative(fftptr, text.data, in, out);
    }
}

void n_fft_r2c_derivative_kspace(NFFTPtr fftptr, const char* name,
                                 fftw_complex* in, fftw_complex* out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_derivative_kspace(fftptr, text.data, in, out);
    }
}

void n_fft_r2c_derivative_nth_kspace(NFFTPtr fftptr, const char* name, int rank,
                                     int nth, fftw_complex* in,
                                     fftw_complex* out)
{
    if (n_string_exist(name, "r2c_3d/") == 1)
    {
        NString text = n_string_split_rest_by_token(name, "/");
        n_fftw_r2c_3d_derivative_nth_kspace(fftptr, text.data, rank, nth, in,
                                            out);
    }
}

void n_fft_setup_f(const char* name) { n_fft_setup(&n_fft, name); }
void n_fft_setup(NFFTPtr fftptr, const char* name)
{
    if (strcmp(name, "r2c_3d") == 0)
    {
        n_fftw_r2c_3d_setup(fftptr);
    }
}

void n_fft_free(NFFTPtr fftptr, const char* name)
{
    if (strcmp(name, "r2c_3d") == 0)
    {
        n_fftw_r2c_3d_free(fftptr);
    }
}
// void fft_forward(const char *name, double *)