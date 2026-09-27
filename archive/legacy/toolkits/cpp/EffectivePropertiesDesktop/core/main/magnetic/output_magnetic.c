#include <effprop/effprop.h>

void output_distribution_magnetic()
{
    // n_vtiFile_3D_double_write(nx, ny, nz, magnetic_potential, "final_magnetic_potential.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,magnetic_field,nx, ny, nz, 3), "out_magnetic_field.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,magnetic_induction,nx, ny, nz, 3), "out_magnetic_induction.vti");
    n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,magnetization,nx, ny, nz, 3), "out_magnetization.vti");
}

void output_effective_property_magnetic(){
    size_t i=0;
    size_t j=0;

    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            permeability_effective[i][j] = permeability_effective[i][j]/NMU0;        
        }
    }

    n_tensor_rank2_print_file("out_effective_permeability.csv",NARR2PTR(double,permeability_effective));
}