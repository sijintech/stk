#include <effprop/effprop.h>

void load_input_magnetoelectric_control()
{
    load_input_magnetic_control();
    load_input_elastic_control();
    load_input_dielectric_control();
}

void load_input_magnetoelectric_boundary_condition()
{
    load_input_magnetic_boundary_condition();
    load_input_elastic_boundary_condition();
    load_input_dielectric_boundary_condition();

}

void load_input_magnetoelectric_solver()
{
    load_input_magnetic_solver();
    load_input_elastic_solver();
    load_input_dielectric_solver();
}

void load_input_magnetoelectric()
{
    load_input_magnetoelectric_control();
    load_input_magnetoelectric_boundary_condition();
    load_input_magnetoelectric_solver();
}