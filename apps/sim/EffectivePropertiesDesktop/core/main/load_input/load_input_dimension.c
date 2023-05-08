#include <effprop/effprop.h>

void load_input_dimension()
{
    nx = n_get_xml_element_as_int("input.xml", "/input/dimension/nx", "", 10);
    ny = n_get_xml_element_as_int("input.xml", "/input/dimension/ny", "", 10);
    nz = n_get_xml_element_as_int("input.xml", "/input/dimension/nz", "", 10);
    dim[0] = nx;
    dim[1] = ny;
    dim[2] = nz;
    dx = n_get_xml_element_as_double("input.xml", "/input/dimension/dx", "", 1e-7);
    dy = n_get_xml_element_as_double("input.xml", "/input/dimension/dy", "", 1e-7);
    dz = n_get_xml_element_as_double("input.xml", "/input/dimension/dz", "", 1e-7);
    delta[0] = dx;
    delta[1] = dy;
    delta[2] = dz;
    phase_count = n_get_xml_element_count("input.xml", "/input/system/material/phase", "");
    // ZF_LOGI("phase count %i",phase_count);
}