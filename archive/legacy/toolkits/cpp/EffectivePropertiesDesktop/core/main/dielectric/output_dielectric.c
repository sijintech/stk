#include <effprop/effprop.h>

void output_distribution_dielectric()
{
    // n_vtiFile_3D_double_write(nx, ny, nz, electric_potential, "out_electric_potential.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,electric_field,nx, ny, nz, 3), "out_electric_field.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,electric_displacement,nx, ny, nz, 3), "out_electric_displacement.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,polarization,nx, ny, nz, 3), "out_polarization.vti");
}

void output_effective_property_dielectric(){
    size_t i=0;
    size_t j=0;
     for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            permittivity_effective[i][j] = permittivity_effective[i][j]/NEPSILON0;        
        }
    }
    n_tensor_rank2_print_file("out_effective_permittivity.csv",NARR2PTR(double,permittivity_effective));
}