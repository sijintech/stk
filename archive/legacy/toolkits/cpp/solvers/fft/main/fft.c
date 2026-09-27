#include "nmathfft/nmathfft.h"

int main(){
    int dim[3]={5,10,15};
    int kdim[3]={0};
    double delta[3]={0.1,0.1,0.1};
    double (*data)[5][10][15];
    NFFT nfft;
    n_fft_data_set(&nfft,"r2c_3d/size",dim);
    n_fft_data_set(&nfft,"r2c_3d/delta",delta);
    n_fft_setup(&nfft,"r2c_3d");
    n_fft_data_get(&nfft,"r2c_3d/ksize",kdim);
    double(*kx)[kdim[0]][kdim[1]][kdim[2]];
    fftw_complex (*kdata)[kdim[0]][kdim[1]][kdim[2]];
    n_data_3D_double_init(kdim[0], kdim[1], kdim[2], &kx);
    n_data_3D_complex_init(kdim[0], kdim[1], kdim[2], &kdata);
    n_data_3D_double_init(5, 10, 15, &data);
    n_data_3D_double_fill(5, 10, 15, *data);

    ZF_LOGD("The kxx 100 %p",kx[1][0][0]);
    ZF_LOGD("The kxx 001 %p",kx[0][0][1]);
    ZF_LOGD("The kxx 000 %p",kx[0][0][0]);
    double *kxx= *kx;
    // n_fft_data_get("r2c_3d/kx",&(*kx)[0][0][0]);
    // n_fft_data_get("r2c_3d/kx",*kx);
    ZF_LOGD("The kszie %i, %i, %i",kdim[0],kdim[1],kdim[2]);
    ZF_LOGD("The kxx %f %f %f",(*kx)[4][9][7],*kx[4][9][7],kx[0]);
    ZF_LOGD("The kxx %f ",kxx[399]);
    ZF_LOGD("The kxx %f ",(*kx)[399]);

    n_fft_forward(&nfft,"r2c_3d", &(*data)[0][0][0], &(*kdata)[0][0][0]);
    ZF_LOGD("The kxx 100 %f",(*kx)[1][0][0]);
    ZF_LOGD("The kxx 001 %f",(*kx)[0][0][1]);
    ZF_LOGD("The kxx 000 %f",(*kx)[0][0][0]);

    return 0;
}