#include <effprop/effprop.h>

void load_input_piezoelectric_control()
{
    load_input_dielectric_control();
    load_input_elastic_control();
}

void load_input_piezoelectric_boundary_condition()
{
    load_input_dielectric_boundary_condition();
    load_input_elastic_boundary_condition();
}

void load_input_piezoelectric_solver()
{
    load_input_dielectric_solver();
    load_input_elastic_solver();
}

void load_input_piezoelectric()
{
    load_input_piezoelectric_control();
    load_input_piezoelectric_boundary_condition();
    load_input_piezoelectric_solver();
}