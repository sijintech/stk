#include <effprop/effprop.h>

void initialize_piezoelectric()
{
    initialize_dielectric();
    initialize_elastic();
    piezoelectric = calloc(phase_count * 27, sizeof(double));
    n_material_generator(piezoelectric, "input.xml", "/input/system/material", "piezoelectric");
}

void destruct_piezoelectric()
{
    free(piezoelectric);
    destruct_dielectric();
    destruct_elastic();
}
