#include "variables.h"

void read_parameter(){
    int nz = n_get_xml_element_as_int("input.xml", "/input/dimension/nz", "", 10);
    int ny = n_get_xml_element_as_int("input.xml", "/input/dimension/ny", "", 10);
    int nx = n_get_xml_element_as_int("input.xml", "/input/dimension/nx", "", 10);
    double dx = n_get_xml_element_as_double("input.xml", "/input/dimension/dx", "", 1e-5);
    double dy = n_get_xml_element_as_double("input.xml", "/input/dimension/dy", "", 1e-5);
    double dz = n_get_xml_element_as_double("input.xml", "/input/dimension/dz", "", 1e-5);
    double Ez = n_get_xml_element_as_double("input.xml", "/input/external/Ez", "", 2e8);
    char choice_format[256]="vti";
    n_get_xml_element_as_string(choice_format, "input.xml", "/input/output/format", "", "vti");
    double breakdown_epsilon[6];
    breakdown_epsilon[0] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon11", "", 1e4);
    breakdown_epsilon[1] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon22", "", 1e4);
    breakdown_epsilon[2] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon33", "", 1e4);
    breakdown_epsilon[3] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon23", "", 0.0);
    breakdown_epsilon[4] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon13", "", 0.0);
    breakdown_epsilon[5] = n_get_xml_element_as_double("input.xml", "/input/material/breakdown/epsilon12", "", 0.0);

    double epsilonR_homo[6];
    epsilonR_homo[0] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon11", "", 1e4);
    epsilonR_homo[1] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon22", "", 1e4);
    epsilonR_homo[2] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon33", "", 1e4);
    epsilonR_homo[3] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon23", "", 0.0);
    epsilonR_homo[4] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon13", "", 0.0);
    epsilonR_homo[5] = n_get_xml_element_as_double("input.xml", "/input/solver/poisson/epsilon12", "", 0.0);
}