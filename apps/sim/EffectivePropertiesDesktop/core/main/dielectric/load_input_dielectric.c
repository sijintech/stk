#include <effprop/effprop.h>

void load_input_dielectric_control()
{
    n_get_xml_element_as_string(control_input_spontaneous_polarization, "input.xml", "/input/system/solver/polarizationSpontaneous", "", "");
    n_get_xml_element_as_string(control_input_charge, "input.xml", "/input/system/solver/charge", "", "");
}

void load_input_dielectric_boundary_condition()
{
    external_electric_field[0] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/x", "", 0);
    external_electric_field[1] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/y", "", 0);
    external_electric_field[2] = n_get_xml_element_as_double("input.xml", "/input/system/external/electricField/z", "", 0);
    n_get_xml_element_as_string(external_electric_field_type, "input.xml", "/input/system/external/electricField/type", "", "constant");
}

void load_input_dielectric_solver()
{
    size_t i=0;
    size_t j=0;
    n_material_generator_one_phase(NARR2PTR(double,permittivity_homo), "input.xml", "/input/system/solver/ref", "permittivity");
    for (i = 0; i < 3; i++)
    {
        for (j = 0; j < 3; j++)
        {
            permittivity_homo[i][j] = permittivity_homo[i][j] * NEPSILON0;
        }
    }
}

void load_input_dielectric()
{
    load_input_dielectric_control();
    load_input_dielectric_boundary_condition();
    load_input_dielectric_solver();
}