#include <effprop/effprop.h>

void initialize_piezomagnetic()
{
    initialize_magnetic();
    initialize_elastic();
    piezomagnetic = calloc(phase_count * 27, sizeof(double));
    n_material_generator(piezomagnetic, "input.xml", "/input/system/material", "piezomagnetic");

}

void destruct_piezomagnetic()
{
    free(piezomagnetic);
    destruct_magnetic();
    destruct_elastic();
}
