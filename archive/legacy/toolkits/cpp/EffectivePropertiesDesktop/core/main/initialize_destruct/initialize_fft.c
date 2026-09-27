#include <effprop/effprop.h>


void initialize_fft()
{
    nfft=calloc(1,sizeof(NFFT));
    n_fft_data_set(nfft,"r2c_3d/size", &(dim[0]));
    n_fft_data_set(nfft,"r2c_3d/delta", &(delta[0]));
    n_fft_setup(nfft,"r2c_3d");
    ZF_LOGI("FFT initialized");
}

void destruct_fft(){
    n_fft_free(nfft,"r2c_3d");
}
