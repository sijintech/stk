#include <effprop/effprop.h>

void output_distribution_thermal()
{
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double, heat_flux,nx, ny, nz, 3), "out_heat_flux.vti");
    n_vtiFile_3D_double_write(nx, ny, nz, NPTR2ARR3D(double,temperature,nx, ny, nz), "out_temperature.vti");
    // n_vtiFile_4D_double_write(nx, ny, nz, 3, temperature_gradient, "out_temperature_gradient.vti");

}

void output_effective_property_thermal(){
    n_tensor_rank2_print_file("out_effective_thermal_conductivity.csv",NARR2PTR(double,thermal_conductivity_effective));
}