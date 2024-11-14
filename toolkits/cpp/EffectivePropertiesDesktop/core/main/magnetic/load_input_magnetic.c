#include <effprop/effprop.h>

void load_input_magnetic_control()
{
    // control_output_electric_field = n_get_xml_element_as_int("input.xml", "/input/output/electricField", "", 0);
    // control_output_electric_potential = n_get_xml_element_as_int("input.xml", "/input/output/electricPotential", "", 0);
}

void load_input_magnetic_boundary_condition()
{
    external_magnetic_field[0] = n_get_xml_element_as_double("input.xml", "/input/system/external/magneticField/x", "", 0);
    external_magnetic_field[1] = n_get_xml_element_as_double("input.xml", "/input/system/external/magneticField/y", "", 0);
    external_magnetic_field[2] = n_get_xml_element_as_double("input.xml", "/input/system/external/magneticField/z", "", 0);
    n_get_xml_element_as_string(external_magnetic_field_type, "input.xml", "/input/system/external/magneticField/type", "", "constant");
}

void load_input_magnetic_solver()
{
    size_t i=0;
    size_t j=0;

    n_material_generator_one_phase(NARR2PTR(double,permeability_homo),"input.xml","/input/system/solver/ref","permeability");
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            permeability_homo[i][j] = permeability_homo[i][j] * NMU0;
        }
    }
}

void load_input_magnetic()
{
    load_input_magnetic_control();
    load_input_magnetic_boundary_condition();
    load_input_magnetic_solver();
}