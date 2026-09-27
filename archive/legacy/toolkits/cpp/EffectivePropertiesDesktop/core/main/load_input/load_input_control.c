#include <effprop/effprop.h>

void load_input_control()
{
    n_get_xml_element_as_string(system_type, "input.xml", "/input/system/type",
                                "", 0);

    if (strcmp(system_type, "dielectric") == 0)
    {
        control_dielectric = 1;
    }
    else if (strcmp(system_type, "diffusion") == 0)
    {
        control_diffusion = 1;
    }
    else if (strcmp(system_type, "electrical") == 0)
    {
        control_electrical = 1;
    }
    else if (strcmp(system_type, "thermal") == 0)
    {
        control_thermal = 1;
    }
    else if (strcmp(system_type, "magnetic") == 0)
    {
        control_magnetic = 1;
    }
    else if (strcmp(system_type, "elastic") == 0)
    {
        control_elastic = 1;
    }
    else if (strcmp(system_type, "piezoelectric") == 0)
    {
        control_piezoelectric = 1;
    }
    else if (strcmp(system_type, "piezomagnetic") == 0)
    {
        control_piezomagnetic = 1;
    }
    else if (strcmp(system_type, "magnetoelectric") == 0)
    {
        control_magnetoelectric = 1;
    }
    // control_dielectric = n_get_xml_element_as_int( "input.xml",
    // "/input/control/dielectric", "", 0); control_diffusion =
    // n_get_xml_element_as_int( "input.xml", "/input/control/diffusion", "",
    // 0); control_electrical = n_get_xml_element_as_int( "input.xml",
    // "/input/control/electrical", "", 0); control_thermal =
    // n_get_xml_element_as_int( "input.xml", "/input/control/thermal", "", 0);
    // control_magnetic = n_get_xml_element_as_int( "input.xml",
    // "/input/control/magnetic", "", 0); control_elastic =
    // n_get_xml_element_as_int( "input.xml", "/input/control/elastic", "", 0);
    // control_piezoelectric = n_get_xml_element_as_int( "input.xml",
    // "/input/control/piezoelectric", "", 0); control_piezomagnetic =
    // n_get_xml_element_as_int( "input.xml", "/input/control/piezomagnetic",
    // "", 0); control_magnetoelectric = n_get_xml_element_as_int( "input.xml",
    // "/input/control/magnetoelectric", "", 0);

    n_get_xml_element_as_string(output_format, "input.xml",
                                "/input/output/format", "", "vti");
    // output_frequency = n_get_xml_element_as_int("input.xml",
    // "/input/output/frequency", "", 100);
    distribution = n_get_xml_element_as_int(
        "input.xml", "/input/system/distribution", "", 0);
}