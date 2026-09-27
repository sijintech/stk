#include "nmathfft/nmathfft.h"

void n_data_1D_complex_add(int n, fftw_complex out[n], fftw_complex in[n])
{
    size_t i=0;
    for (i = 0; i < n; i++)
    {
        out[i] = out[i] + in[i];
    }
}


void n_data_complex_get_nth_component(int total, int rank, int nth, fftw_complex out[total], fftw_complex in[total][rank]){
    size_t i=0;
    for (i = 0; i < total; i++)
    {
        out[i] = in[i][nth];
    }
}

void n_data_complex_set_nth_component(int total, int rank, int nth, fftw_complex out[total][rank], fftw_complex in[total]){
    size_t i=0;
    for (i = 0; i < total; i++)
    {
        out[i][nth] = in[i];
    }
}