#include <nmaterialgenerator/material.h>

// nonzero, unique, independent

//     0, //  1: 1, C1
//     0, //  2: \bar{1}, S2
const PointGroup general_rank2_triclinic = {9,
                                            6,
                                            6,
                                            {{1, {"11"}},
                                             {1, {"22"}},
                                             {1, {"33"}},
                                             {2, {"12", "21"}},
                                             {2, {"13", "31"}},
                                             {2, {"23", "32"}}}};

//     1, //  3: 2, C2
//     1, //  4: m, C1h, C1v, Cs
//     1, //  5: 2/m, C2h
const PointGroup general_rank2_monoclinic = {
    5, 4, 4, {{1, {"11"}}, {1, {"22"}}, {1, {"33"}}, {2, {"13", "31"}}}};

//     2, //  6: 222, D2
//     2, //  7: mm2, C2v
//     2, //  8: mmm, D2h
const PointGroup general_rank2_orthorhombic = {
    3, 3, 3, {{1, {"11"}}, {1, {"22"}}, {1, {"33"}}}};

//     3, //  9: 4, C4
//     3, // 10: \bar{4}, S4
//     3, // 11: 4/m, C4h
//     3, // 12: 422, D4
//     3, // 13: 4mm, C4v
//     3, // 14: \bar{4}2m, D2d
//     3, // 15: 4/m mm, D4h
//     3, // 16: 3, C3
//     3, // 17: \bar{3}, S6, C3i
//     3, // 18: 32, D3
//     3, // 19: 3m, C3v
//     3, // 20: \bar{3} m, D3d
//     3, // 21: 6, C6
//     3, // 22: \bar{6}, C3h
//     3, // 23: 6/m, C6h
//     3, // 24: 622, D6
//     3, // 25: 6mm, C6v
//     3, // 26: \bar{6}m2, D3h
//     3, // 27: 6/m mm, D6h
//     3, // 33: curie1

const PointGroup general_rank2_uniaxial = {
    3, 2, 2, {{2, {"11", "22"}}, {1, {"33"}}}};

//     4, // 28: 23, T
//     4, // 29: m\bar{3}, Th
//     4, // 30: 432, O
//     4, // 31: \bar{4}3m, Td
//     4, // 32: m\bar{3}m, Oh
//     4  // 34: curie2
const PointGroup general_rank2_cubic = {3, 1, 1, {{3, {"11", "22", "33"}}}};

PointGroup _general_rank2_get_PointGroup(const char* point_group) {
    if (strcmp(point_group, "triclinic") == 0) {
        return general_rank2_triclinic;
    } else if (strcmp(point_group, "monoclinic") == 0) {
        return general_rank2_monoclinic;
    } else if (strcmp(point_group, "orthorhombic") == 0) {
        return general_rank2_orthorhombic;
    } else if (strcmp(point_group, "uniaxial") == 0) {
        return general_rank2_uniaxial;
    } else if (strcmp(point_group, "cubic") == 0) {
        return general_rank2_cubic;
    }
    return general_rank2_cubic;
}

void n_material_generator_tensor_rank2(double* tensor,
                                               const char* filename,
                                               const char* xpathText) {
    // custom
    // point group
    // isotropic as default
                printf("in loo1");

    char temp[MAX_STRING] = {'\0'};
                    ZF_LOGI("in loo11");
    int gpindex = 4;
    int k = 0;
    double value = 0;
    char point_group[10] = "cubic\0";

    sprintf(temp, "%s%s", xpathText, "/pointGroup");
                ZF_LOGI("in loo %s 2",temp);
    n_get_xml_element_as_string(point_group, filename, temp, "", "cubic");
            ZF_LOGI("in loo1");

    PointGroup pg = general_rank2_cubic;
    ComponentValue* cv;
    pg = _general_rank2_get_PointGroup(point_group);
    cv = calloc(pg.unique, sizeof(ComponentValue));
    char index_string[5] = {'\0'};
            ZF_LOGI("in loo2");

    // set independent component
    int component_count = 0;
    sprintf(temp, "%s%s", xpathText, "/component");
    component_count = n_get_xml_element_count(filename, temp, "");
                ZF_LOGI("in loo3");

    if (component_count != pg.independent) {
        ZF_LOGE("The number of component is not suitable for the symmetry you "
                "choose!");
    } else {
        for (k = 0; k < component_count; k++) {
            sprintf(
                temp, "%s%s%i%s", xpathText, "/component[", k + 1, "]/value");
            ZF_LOGI("in loop %i %s",k,temp);
            value = n_get_xml_element_as_double(filename, temp, "", 0);

            sprintf(temp,
                    "%s%s%i%s",
                    xpathText,
                    "/component[",
                    k + 1,
                    "]/index[1]");
            n_get_xml_element_as_string(
                index_string, filename, temp, "", "index");
            cv[k].value = value;
            strcpy(cv[k].index, index_string);
        }
    }
    // set dependent component
    ZF_LOGI("The rank 2 tensor %i %f",pg.unique,cv[0].value);

    n_material_generate_tensor(tensor, pg.unique, pg.relation, cv);
    free(cv);
}
