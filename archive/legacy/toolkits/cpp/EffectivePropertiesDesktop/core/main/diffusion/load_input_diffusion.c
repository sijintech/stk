#include <effprop/effprop.h>

void load_input_diffusion_control()
{
    // control_output_electric_field = n_get_xml_element_as_int("input.xml", "/input/output/electricField", "", 0);
    // control_output_electric_potential = n_get_xml_element_as_int("input.xml", "/input/output/electricPotential", "", 0);
}

void load_input_diffusion_boundary_condition()
{
    external_concentration_gradient[0] = n_get_xml_element_as_double("input.xml", "/input/system/external/concentrationGradient/x", "", 0);
    external_concentration_gradient[1] = n_get_xml_element_as_double("input.xml", "/input/system/external/concentrationGradient/y", "", 0);
    external_concentration_gradient[2] = n_get_xml_element_as_double("input.xml", "/input/system/external/concentrationGradient/z", "", 0);
    n_get_xml_element_as_string(external_concentration_gradient_type, "input.xml", "/input/system/external/concentrationGradient/type", "", "constant");
}

void load_input_diffusion_solver()
{
    n_material_generator_one_phase(NARR2PTR(double,diffusivity_homo),"input.xml","/input/system/solver/ref","diffusivity");
}

void load_input_diffusion()
{
    load_input_diffusion_control();
    load_input_diffusion_boundary_condition();
    load_input_diffusion_solver();
}