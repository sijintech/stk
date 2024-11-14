#include <effprop/effprop.h>

void output_distribution_electrical()
{
    // n_vtiFile_3D_double_write(nx, ny, nz, electric_potential, "out_electric_potential.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,electric_field,nx, ny, nz, 3), "out_electric_field.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,electrical_current,nx, ny, nz, 3), "out_electrical_current.vti");
}

void output_effective_property_electrical(){
    n_tensor_rank2_print_file("out_effective_electrical_conductivity.csv",NARR2PTR(double,electrical_conductivity_effective));
}