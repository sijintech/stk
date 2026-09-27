#include <effprop/effprop.h>

void output_distribution_magnetoelectric()
{
    output_distribution_magnetic();
    output_distribution_elastic();
    output_distribution_dielectric();
}

void output_effective_property_magnetoelectric(){
    output_effective_property_magnetic();
    output_effective_property_elastic();
    output_effective_property_dielectric();
    n_tensor_rank2_print_file("out_effective_magnetoelectric.csv",NARR2PTR(double,magnetoelectric_effective));
}