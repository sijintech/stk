#include <effprop/effprop.h>

void load_input_electrical_control()
{
    // control_output_electric_field = n_get_xml_element_as_int("input.xml", "/input/output/electricField", "", 0);
    // control_output_electric_potential = n_get_xml_element_as_int("input.xml", "/input/output/electricPotential", "", 0);
}

void load_input_electrical_boundary_condition()
{
    external_electric_field[0] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/x", "", 0);
    external_electric_field[1] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/y", "", 0);
    external_electric_field[2] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/z", "", 0);
    n_get_xml_element_as_string(external_electric_field_type, "input.xml", "/input/system/external/electricField/type", "", "constant");
}

void load_input_electrical_solver()
{
    n_material_generator_one_phase(NARR2PTR(double,electrical_conductivity_homo),"input.xml","/input/system/solver/ref","electrical_conductivity");
    iter_step = n_get_xml_element_as_double("input.xml", "/input/system/solver/iterStep", "", 0.2);
    iter_error = n_get_xml_element_as_double("input.xml", "/input/system/solver/threshold", "", 1e-4);
}

void load_input_electrical()
{
    load_input_electrical_control();
    load_input_electrical_boundary_condition();
    load_input_electrical_solver();
}