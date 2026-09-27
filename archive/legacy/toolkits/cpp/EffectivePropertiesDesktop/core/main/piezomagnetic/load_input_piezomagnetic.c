#include <effprop/effprop.h>

void load_input_piezomagnetic_control()
{
    load_input_magnetic_control();
    load_input_elastic_control();
}

void load_input_piezomagnetic_boundary_condition()
{
    load_input_magnetic_boundary_condition();
    load_input_elastic_boundary_condition();
}

void load_input_piezomagnetic_solver()
{
    load_input_magnetic_solver();
    load_input_elastic_solver();
}

void load_input_piezomagnetic()
{
    load_input_piezomagnetic_control();
    load_input_piezomagnetic_boundary_condition();
    load_input_piezomagnetic_solver();
}