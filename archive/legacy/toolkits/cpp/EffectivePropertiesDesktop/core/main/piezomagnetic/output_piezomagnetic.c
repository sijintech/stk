#include <effprop/effprop.h>

void output_distribution_piezomagnetic() {
    output_distribution_magnetic();
    output_distribution_elastic();
}

void output_effective_property_piezomagnetic() {
    output_effective_property_magnetic();
    output_effective_property_elastic();
    n_material_tensor_print_file_piezomagnetic(
        "out_effective_piezomagnetic.csv",
        NARR2PTR(double, piezomagnetic_effective));
}