#include <effprop/effprop.h>

void load_input_thermal_control()
{
    // control_output_electric_field = n_get_xml_element_as_int("input.xml", "/input/output/electricField", "", 0);
    // control_output_electric_potential = n_get_xml_element_as_int("input.xml", "/input/output/electricPotential", "", 0);
}

void load_input_thermal_boundary_condition()
{
    external_temperature_gradient[0] = n_get_xml_element_as_double("input.xml", "/input/system/external/temperatureGradient/x", "", 0);
    external_temperature_gradient[1] = n_get_xml_element_as_double("input.xml", "/input/system/external/temperatureGradient/y", "", 0);
    external_temperature_gradient[2] = n_get_xml_element_as_double("input.xml", "/input/system/external/temperatureGradient/z", "", 0);
    n_get_xml_element_as_string(external_temperature_gradient_type, "input.xml", "/input/system/external/temperatureGradient/type", "", "constant");
}

void load_input_thermal_solver()
{
    n_material_generator_one_phase(NARR2PTR(double,thermal_conductivity_homo),"input.xml","/input/system/solver/ref","thermal_conductivity");
}

void load_input_thermal()
{
    load_input_thermal_control();
    load_input_thermal_boundary_condition();
    load_input_thermal_solver();
}