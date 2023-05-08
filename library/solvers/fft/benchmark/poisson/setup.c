#include "variables.h"

void setup_fftw(){
    int dim[3]={nx,ny,nz};
    // int kdim[3]={0};
    double delta[3]={dx,dy,dz};
    n_fft_data_set(&nfft,"r2c_3d/size",dim);
    n_fft_data_set(&nfft,"r2c_3d/delta",delta);
    n_fft_setup(&nfft,"r2c_3d");
    // n_fft_data_get(&nfft,"r2c_3d/ksize",kdim);
}

void setup_structure(){
    n_material_generator(*epsilonR,"input.xml","/input/material","permitivity");
}

void setup_poisson(){
    n_fft_poisson_init(psp,&nfft);

    n_fft_poisson_data_set(psp,"poisson_3d/epsilon_homo",epsilonR_homo);
    n_fft_poisson_data_link(psp,"poisson_3d/epsilon",epsilonR);

    n_fft_poisson_setup(psp);
}