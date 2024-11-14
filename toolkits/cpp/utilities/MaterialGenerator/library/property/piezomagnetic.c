#include <nmaterialgenerator/material.h>

// nonzero, unique, independent

// \bar{1}(S2), 2/m, mmm, \bar{3}, \bar{3}m, 4/m, 4/mmm, 6/m, 6/mmm, m3, 432,
// m3m, inf/m, inf/mm, infinf, infinfm
const PointGroup piezomagnetic_none = {0, 0, 0, {}};

//  1(C1), \bar{1}(S2)
const PointGroup piezomagnetic_1 = {27,
                                    18,
                                    18,
                                    {{1, {"111"}},
                                     {1, {"122"}},
                                     {1, {"133"}},
                                     {2, {"123", "132"}},
                                     {2, {"113", "131"}},
                                     {2, {"121", "112"}},
                                     {1, {"211"}},
                                     {1, {"222"}},
                                     {1, {"233"}},
                                     {2, {"223", "232"}},
                                     {2, {"213", "231"}},
                                     {2, {"221", "212"}},
                                     {1, {"311"}},
                                     {1, {"322"}},
                                     {1, {"333"}},
                                     {2, {"323", "332"}},
                                     {2, {"313", "331"}},
                                     {2, {"321", "312"}}}};

// 2(C2), m(C1h, C1v, Cs), 2/m(C2h)
const PointGroup piezomagnetic_2 = {13,
                                    8,
                                    8,
                                    {{2, {"123", "132"}},
                                     {2, {"121", "112"}},
                                     {1, {"211"}},
                                     {1, {"222"}},
                                     {1, {"233"}},
                                     {2, {"213", "231"}},
                                     {2, {"323", "332"}},
                                     {2, {"321", "312"}}}};

//  2', m', 2'/m'
const PointGroup piezomagnetic_2prime = {14,
                                         10,
                                         10,
                                         {{1, {"111"}},
                                          {1, {"122"}},
                                          {1, {"133"}},
                                          {2, {"113", "131"}},
                                          {2, {"223", "232"}},
                                          {2, {"221", "212"}},
                                          {1, {"311"}},
                                          {1, {"322"}},
                                          {1, {"333"}},
                                          {2, {"313", "331"}}}};

//  222(D2), mm2(C2v), mmm(D2h)
const PointGroup piezomagnetic_222 = {
    6, 3, 3, {{2, {"123", "132"}}, {2, {"213", "231"}}, {2, {"312", "321"}}}};

//  2'2'2, m'm'2, m'2'm, m'm'm
const PointGroup piezomagnetic_2prime2prime2 = {7,
                                                5,
                                                5,
                                                {{2, {"113", "131"}},
                                                 {2, {"223", "232"}},
                                                 {1, {"311"}},
                                                 {1, {"322"}},
                                                 {1, {"333"}}}};

//  3(C3), \bar{3}(S6, C3i)
const PointGroup piezomagnetic_3 = {19,
                                    5,
                                    5,
                                    {
                                        {4, {"111", "-122", "-221", "-212"}},
                                        {4, {"-211", "222", "-121", "-112"}},
                                        {4, {"123", "132", "-213", "-231"}},
                                        {4, {"113", "131", "223", "232"}},
                                        {2, {"311", "322"}},
                                        {1, {"333"}},
                                    }};

//  32(D3), 3m, \bar{3}m
const PointGroup piezomagnetic_32 = {8,
                                     2,
                                     2,
                                     {
                                         {4, {"111", "-122", "-221", "-212"}},
                                         {4, {"123", "132", "-213", "-231"}},
                                     }};

//  32', 3m', \bar{3}m'
const PointGroup piezomagnetic_32prime = {
    11,
    4,
    4,
    {
        {4, {"-211", "222", "-121", "-112"}},
        {4, {"113", "131", "223", "232"}},
        {2, {"311", "322"}},
        {1, {"333"}},
    }};

//  4, \bar{4}, 4/m, 6, \bar{6}, 6/m, inf, inf/m
const PointGroup piezomagnetic_4 = {11,
                                    4,
                                    4,
                                    {
                                        {4, {"123", "132", "-213", "-231"}},
                                        {4, {"113", "131", "223", "232"}},
                                        {2, {"311", "322"}},
                                        {1, {"333"}},
                                    }};

//  4', \bar{4}',4'/m
const PointGroup piezomagnetic_4prime = {
    12,
    4,
    4,
    {
        {4, {"123", "132", "213", "231"}},
        {4, {"113", "131", "-223", "-232"}},
        {2, {"311", "-322"}},
        {2, {"312", "321"}},
    }};

//  422(D4), 4mm, \bar{4}2m, 4/mmm, 622(D6), 6mm, \bar{6}m2, 6/mmm, inf2
const PointGroup piezomagnetic_422 = {
    4, 1, 1, {{4, {"123", "132", "-213", "-231"}}}};

//  4'22,4'mm',\bar{4}'2m',\bar{4}'2'm, 4'/mmm'
const PointGroup piezomagnetic_4prime22 = {
    6, 2, 2, {{4, {"123", "132", "213", "231"}}, {2, {"312", "321"}}}};

//  42'2',4m'm',\bar{4}2'm',4/mm'm',62'2',6m'm',
//  \bar{6}m'2',6/mm'm',inf2',inf/mm'
const PointGroup piezomagnetic_42prime2prime = {
    7,
    3,
    3,
    {{4, {"113", "131", "223", "232"}}, {2, {"311", "322"}}, {1, {"333"}}}};

//  6', \bar{6}', 6'/m'
const PointGroup piezomagnetic_6prime = {
    8,
    2,
    2,
    {{4, {"111", "-122", "-221", "-212"}},
     {4, {"-211", "222", "-121", "-112"}}}};

//  6'22', 6'm',\bar{6}'m'2,\bar{6}'m2', 6'/m'mm'
const PointGroup piezomagnetic_6prime22prime = {
    8, 2, 2, {{4, {"111", "-122", "-221", "-212"}}}};

//  23, m\bar{3}, 4'32, \bar{4}'3m,',m\bar{3}m'
const PointGroup piezomagnetic_23 = {
    6, 1, 1, {{6, {"123", "132", "213", "231", "312", "321"}}}};

PointGroup _piezomagnetic_get_PointGroup(const char* point_group) {
    if (strcmp(point_group, "1") == 0) {
        return piezomagnetic_1;
    } else if (strcmp(point_group, "2") == 0) {
        return piezomagnetic_2;
    } else if (strcmp(point_group, "2prime") == 0) {
        return piezomagnetic_2prime;
    } else if (strcmp(point_group, "222") == 0) {
        return piezomagnetic_222;
    } else if (strcmp(point_group, "2prime2prime2") == 0) {
        return piezomagnetic_2prime2prime2;
    } else if (strcmp(point_group, "3") == 0) {
        return piezomagnetic_3;
    } else if (strcmp(point_group, "32") == 0) {
        return piezomagnetic_32;
    } else if (strcmp(point_group, "32prime") == 0) {
        return piezomagnetic_32prime;
    } else if (strcmp(point_group, "4") == 0) {
        return piezomagnetic_4;
    } else if (strcmp(point_group, "4prime") == 0) {
        return piezomagnetic_4prime;
    } else if (strcmp(point_group, "422") == 0) {
        return piezomagnetic_422;
    } else if (strcmp(point_group, "4prime22") == 0) {
        return piezomagnetic_4prime22;
    } else if (strcmp(point_group, "42prime2prime") == 0) {
        return piezomagnetic_42prime2prime;
    } else if (strcmp(point_group, "6prime") == 0) {
        return piezomagnetic_6prime;
    } else if (strcmp(point_group, "6prime22prime") == 0) {
        return piezomagnetic_6prime22prime;
    } else if (strcmp(point_group, "23") == 0) {
        return piezomagnetic_23;
    }
    return piezomagnetic_none;
}

void _piezomagnetic_voigt_to_tensor(double* value, char* index) {
    if (strlen(index) == 2) {
        // needs to convert voigt to tensor
        switch (index[1]) {
            case '1':
                index[2] = '1';
            case '2':
                index[2] = '2';
            case '3':
                index[2] = '3';
            case '4':
                index[1] = '2';
                index[2] = '3';
            case '5':
                index[1] = '1';
                index[2] = '3';
            case '6':
                index[1] = '1';
                index[2] = '2';
            default:
                ZF_LOGE("The index is wrong %s", *index);
        }
        index[3] = '\0';
        if (index[1] - '0' <= 3) {
            // the right half of
            *value = *value / 2;
        }
    }
}

void n_material_generator_tensor_piezomagnetic(double* tensor,
                                               const char* filename,
                                               const char* xpathText) {
    // custom
    // point group
    // isotropic as default
    char temp[MAX_STRING] = {'\0'};
    int gpindex = 4;
    int k = 0;
    double value = 0;
    char point_group[10] = "none\0";
    sprintf(temp, "%s%s", xpathText, "/pointGroup");
    n_get_xml_element_as_string(point_group, filename, temp, "", "none");

    PointGroup pg = piezomagnetic_none;
    ComponentValue* cv;
    pg = _piezomagnetic_get_PointGroup(point_group);
    cv = calloc(pg.unique, sizeof(ComponentValue));
    char index_string[10] = {'\0'};

    // set independent component
    int component_count = 0;
    sprintf(temp, "%s%s", xpathText, "/component");
    component_count = n_get_xml_element_count(filename, temp, "");
    if (component_count != pg.independent) {
        ZF_LOGE("The number of component is not suitable for the symmetry you "
                "choose!");
    } else {

        for (k = 0; k < component_count; k++) {
            sprintf(
                temp, "%s%s%i%s", xpathText, "/component[", k + 1, "]/value");
            value = n_get_xml_element_as_double(filename, temp, "", 0);

            sprintf(temp,
                    "%s%s%i%s",
                    xpathText,
                    "/component[",
                    k + 1,
                    "]/index[1]");
            n_get_xml_element_as_string(
                index_string, filename, temp, "", "index");

            _piezomagnetic_voigt_to_tensor(&value, index_string);

            cv[k].value = value;
            strcpy(cv[k].index, index_string);
            index_string[0] = '\0';
        }
    }

    // set dependent component

    n_material_generate_tensor(tensor, pg.unique, pg.relation, cv);
    free(cv);
}

void n_material_tensor_print_piezomagnetic(double* tensor, const char* name) {
    int i = 0;
    ZF_LOGI(
        "---------Begin piezomagnetic tensor in Voigt notation %s-------------",
        name);
    int row[6] = {0, 12, 24};
    for (i = 0; i < 3; i++) {
        ZF_LOGI("%i1=%10.3le %i2=%10.3le %i3=%10.3le %i4=%10.3le %i5=%10.3le "
                "%i6=%10.3le",
                i + 1,
                tensor[row[i]],
                i + 1,
                tensor[row[i] + 3 * 1 + 1],
                i + 1,
                tensor[row[i] + 3 * 2 + 2],
                i + 1,
                tensor[row[i] + 3 * 1 + 2],
                i + 1,
                tensor[row[i] + 3 * 0 + 2],
                i + 1,
                tensor[row[i] + 3 * 0 + 1]);
    }
    ZF_LOGI(
        "--------- End piezomagnetic tensor in Voigt notation %s -------------",
        name);
}

void n_material_tensor_print_file_piezomagnetic(const char* name,
                                                double* tensor) {
    int i = 0;
    FILE* fp;

    int row[6] = {0, 12, 24};
    fp = fopen(name, "w");
    fprintf(fp, "Index,1,2,3,4,5,6\n");
    for (i = 0; i < 3; i++) {
        fprintf(fp,
                "%i,%10.3le,%10.3le,%10.3le,%10.3le,%10.3le,%10.3le\n",
                i + 1,
                tensor[row[i]],
                tensor[row[i] + 3 * 1 + 1],
                tensor[row[i] + 3 * 2 + 2],
                tensor[row[i] + 3 * 1 + 2],
                tensor[row[i] + 3 * 0 + 2],
                tensor[row[i] + 3 * 0 + 1]);
    }
}