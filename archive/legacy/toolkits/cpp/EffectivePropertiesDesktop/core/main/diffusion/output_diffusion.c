#include <effprop/effprop.h>

void output_distribution_diffusion()
{
    n_vtiFile_3D_double_write(nx, ny, nz, NPTR2ARR3D(double, concentration,nx, ny, nz), "out_concentration.vti");
    // n_vtiFile_4D_double_write(nx, ny, nz, 3, concentration_gradient, "out_concentration_gradient.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,molar_flux,nx, ny, nz, 3), "out_molar_flux.vti");
}

void output_effective_property_diffusion(){
    n_tensor_rank2_print_file("out_effective_diffusivity.csv",NARR2PTR(double,diffusivity_effective));
}