#include <nmaterialgenerator/material.h>

const PointGroup general_rank0 = {1, 1, 1, {{1, {"1"}}}};

void n_material_generator_tensor_general_rank0(double* tensor,
                                               const char* filename,
                                               const char* xpathText) {
    char temp[MAX_STRING] = {'\0'};
    int gpindex = 4;
    int k = 0;
    double value = 0;
    char point_group[10] = "custom\0";

    PointGroup pg = general_rank0;
    ComponentValue* cv;
    cv = calloc(pg.unique, sizeof(ComponentValue));
    char index_string[5] = "1\0";

    sprintf(temp, "%s%s", xpathText, "/component[1]/value");
    value = n_get_xml_element_as_double(filename, temp, "", 0);

    cv[0].value = value;
    strcpy(cv[0].index, index_string);

    n_material_generate_tensor(tensor, pg.unique, pg.relation, cv);
    free(cv);
}