#include <effprop/effprop.h>

void initialize_magnetoelectric()
{

    initialize_magnetic();
    initialize_dielectric();
    initialize_elastic();
    piezomagnetic = calloc(phase_count * 27, sizeof(double));
    piezoelectric = calloc(phase_count * 27, sizeof(double));
    magnetoelectric = calloc(phase_count * 9, sizeof(double));

    n_material_generator(piezomagnetic, "input.xml", "/input/system/material", "piezomagnetic");
    n_material_generator(piezoelectric, "input.xml", "/input/system/material", "piezoelectric");
    n_material_generator(magnetoelectric, "input.xml", "/input/system/material", "magnetoelectric");

}

void destruct_magnetoelectric()
{
    free(piezomagnetic);
    free(piezoelectric);
    free(magnetoelectric);
    destruct_dielectric();
    destruct_magnetic();
    destruct_elastic();
}
