#include <effprop/effprop.h>

void output_distribution_piezoelectric() {
    output_distribution_dielectric();
    output_distribution_elastic();
}

void output_effective_property_piezoelectric() {
    output_effective_property_dielectric();
    output_effective_property_elastic();
    n_material_tensor_print_file_piezoelectric(
        "out_effective_piezoelectric.csv",
        NARR2PTR(double, piezoelectric_effective));
}