#include <effprop/effprop.h>

void output_distribution_elastic() {
    n_vtiFile_4D_double_write(nx,
                              ny,
                              nz,
                              6,
                              NPTR2ARR4D(double, stress, nx, ny, nz, 6),
                              "out_stress.vti");
    n_vtiFile_4D_double_write(nx,
                              ny,
                              nz,
                              6,
                              NPTR2ARR4D(double, strain, nx, ny, nz, 6),
                              "out_strain.vti");
    // n_vtiFile_4D_double_write(nx, ny, nz, 3, displacement,
    // "out_displacement.vti");
}

void output_effective_property_elastic() {
    n_material_tensor_print_file_stiffness(
        "out_effective_stiffness.csv", NARR2PTR(double, stiffness_effective));
}