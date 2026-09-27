#include <effprop/effprop.h>

void load_input_elastic_control()
{
    // control_output_stress = n_get_xml_element_as_int("input.xml",
    // "/input/output/stress", "", 0); control_output_strain =
    // n_get_xml_element_as_int("input.xml", "/input/output/strain", "", 0);
}

void load_input_elastic_boundary_condition()
{
    external_stress[0][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor11", "", 0);
    external_stress[0][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor12", "", 0);
    external_stress[0][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor13", "", 0);
    external_stress[1][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor22", "", 0);
    external_stress[1][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor23", "", 0);
    external_stress[2][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor33", "", 0);
    external_stress[1][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor21", "",
        external_stress[0][1]);
    external_stress[2][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor31", "",
        external_stress[0][2]);
    external_stress[2][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/stress/tensor32", "",
        external_stress[1][2]);

    external_strain[0][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor11", "", 0);
    external_strain[0][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor12", "", 0);
    external_strain[0][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor13", "", 0);
    external_strain[1][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor22", "", 0);
    external_strain[1][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor23", "", 0);
    external_strain[2][2] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor33", "", 0);
    external_strain[1][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor21", "",
        external_strain[0][1]);
    external_strain[2][0] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor31", "",
        external_strain[0][2]);
    external_strain[2][1] = n_get_xml_element_as_double(
        "input.xml", "/input/system/external/elastic/strain/tensor32", "",
        external_strain[1][2]);
    n_get_xml_element_as_string(external_elastic_type, "input.xml",
                                "/input/system/external/elastic/type", "",
                                "strain");
}

void load_input_elastic_solver()
{
    // need to change, we should use the material setup from
    // nstructure-generator stiffness_homo[0][0] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo11", "", 0); stiffness_homo[1][1] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo22", "", 0); stiffness_homo[2][2] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo33", "", 0); stiffness_homo[1][2] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo23", "", 0); stiffness_homo[0][2] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo13", "", 0); stiffness_homo[0][1] =
    // n_get_xml_element_as_double("input.xml",
    // "/input/solver/electric/epsilonHomo12", "", 0); stiffness_homo[2][1] =
    // permittivity_homo[1][2]; stiffness_homo[2][0] = permittivity_homo[0][2];
    // stiffness_homo[1][0] = permittivity_homo[0][1];
    n_material_generator_one_phase(NARR2PTR(double, stiffness_homo),
                                   "input.xml", "/input/system/solver/ref",
                                   "stiffness");

    // ZF_LOGI("after loa input solver");
}

void load_input_elastic()
{
    load_input_elastic_control();
    if (distribution == 1)
    {

        load_input_elastic_boundary_condition();
    }
    load_input_elastic_solver();
}