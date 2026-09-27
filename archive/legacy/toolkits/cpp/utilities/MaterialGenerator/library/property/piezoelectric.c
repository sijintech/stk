#include <nmaterialgenerator/material.h>

// nonzero, unique, independent

// \bar{1}(S2), 2/m, mmm, \bar{3}, \bar{3}m, 4/m, 4/mmm, 6/m, 6/mmm, m3, 432,
// m3m, inf/m, inf/mm, infinf, infinfm
const PointGroup piezoelectric_none = {0, 0, 0, {}};

//  1(C1)
const PointGroup piezoelectric_1 = {27,
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

//  2(C2)
const PointGroup piezoelectric_2 = {13,
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

//  m(C1h, C1v, Cs)
const PointGroup piezoelectric_m = {13,
                                    8,
                                    8,
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

//  mm2(C2v)
const PointGroup piezoelectric_mm2 = {7,
                                      5,
                                      5,
                                      {{2, {"113", "131"}},
                                       {2, {"223", "232"}},
                                       {1, {"311"}},
                                       {1, {"322"}},
                                       {1, {"333"}}}};

//  222(D2)
const PointGroup piezoelectric_222 = {
    6, 3, 3, {{2, {"123", "132"}}, {2, {"213", "231"}}, {2, {"312", "321"}}}};

//  3(C3)
const PointGroup piezoelectric_3 = {19,
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

//  32(D3)
const PointGroup piezoelectric_32 = {8,
                                     2,
                                     2,
                                     {
                                         {4, {"111", "-122", "-221", "-212"}},
                                         {4, {"123", "132", "-213", "-231"}},
                                     }};

//  3m(C3v)
const PointGroup piezoelectric_3m = {11,
                                     4,
                                     4,
                                     {
                                         {4, {"-211", "222", "-121", "-112"}},
                                         {4, {"113", "131", "223", "232"}},
                                         {2, {"311", "322"}},
                                         {1, {"333"}},
                                     }};

//  4(C4), 6(C6), inf
const PointGroup piezoelectric_46inf = {11,
                                        4,
                                        4,
                                        {
                                            {4, {"123", "132", "-213", "-231"}},
                                            {4, {"113", "131", "223", "232"}},
                                            {2, {"311", "322"}},
                                            {1, {"333"}},
                                        }};

//  \bar{4}(S4)
const PointGroup piezoelectric_bar4 = {12,
                                       4,
                                       4,
                                       {
                                           {4, {"123", "132", "213", "231"}},
                                           {4, {"113", "131", "-223", "-232"}},
                                           {2, {"311", "-322"}},
                                           {2, {"312", "321"}},
                                       }};

//  4mm(C4v), 6mm(C6v), infm
const PointGroup piezoelectric_4mm6mminfm = {
    7,
    3,
    3,
    {
        {4, {"113", "131", "223", "232"}},
        {2, {"311", "322"}},
        {1, {"333"}},
    }};

//  422(D4), 622(D6), inf2
const PointGroup piezoelectric_422622inf2 = {
    4, 1, 1, {{4, {"123", "132", "-213", "-231"}}}};

//  \bar{4}2m(D2d)
const PointGroup piezoelectric_bar42m = {
    6, 2, 2, {{4, {"123", "132", "213", "231"}}, {2, {"312", "321"}}}};

//  \bar{6}(C3h)
const PointGroup piezoelectric_bar6 = {8,
                                       2,
                                       2,
                                       {
                                           {4, {"111", "-122", "-221", "-212"}},
                                           {4, {"-211", "222", "-121", "-112"}},
                                       }};

//  \bar{6}m2(D3h)
const PointGroup piezoelectric_bar6m2 = {
    4, 1, 1, {{4, {"-211", "222", "-121", "-112"}}}};

//  \bar{4}3m()
const PointGroup piezoelectric_bar43m23 = {
    6, 1, 1, {{6, {"123", "132", "213", "231", "312", "321"}}}};

PointGroup _piezoelectric_get_PointGroup(const char* point_group) {
    if (strcmp(point_group, "1") == 0) {
        return piezoelectric_1;
    } else if (strcmp(point_group, "2") == 0) {
        return piezoelectric_2;
    } else if (strcmp(point_group, "m") == 0) {
        return piezoelectric_m;
    } else if (strcmp(point_group, "mm2") == 0) {
        return piezoelectric_mm2;
    } else if (strcmp(point_group, "222") == 0) {
        return piezoelectric_222;
    } else if (strcmp(point_group, "3") == 0) {
        return piezoelectric_3;
    } else if (strcmp(point_group, "32") == 0) {
        return piezoelectric_32;
    } else if (strcmp(point_group, "3m") == 0) {
        return piezoelectric_3m;
    } else if (strcmp(point_group, "4") == 0) {
        return piezoelectric_46inf;
    } else if (strcmp(point_group, "bar4") == 0) {
        return piezoelectric_bar4;
    } else if (strcmp(point_group, "4mm") == 0) {
        return piezoelectric_4mm6mminfm;
    } else if (strcmp(point_group, "422") == 0) {
        return piezoelectric_422622inf2;
    } else if (strcmp(point_group, "bar42m") == 0) {
        return piezoelectric_bar42m;
    } else if (strcmp(point_group, "bar6") == 0) {
        return piezoelectric_bar6;
    } else if (strcmp(point_group, "bar6m2") == 0) {
        return piezoelectric_bar6m2;
    } else if (strcmp(point_group, "bar43m") == 0) {
        return piezoelectric_bar43m23;
    }
    return piezoelectric_none;
}

void _piezoelectric_voigt_to_tensor(double* value, char* index) {
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
                ZF_LOGE("Problem with the voigt index %s", index);
        }
        index[3] = '\0';
        if (index[1] - '0' <= 3) {
            // the right half of
            *value = *value / 2;
        }
    }
}

void n_material_generator_tensor_piezoelectric(double* tensor,
                                               const char* filename,
                                               const char* xpathText) {
    // custom
    // point group
    // isotropic as default
    char temp[MAX_STRING] = {'\0'};
    int gpindex = 4;
    int k = 0;
    double value = 0;
    char point_group[20] = "none\0";
    sprintf(temp, "%s%s", xpathText, "/pointGroup");
    n_get_xml_element_as_string(point_group, filename, temp, "", "none");

    PointGroup pg = piezoelectric_none;
    ComponentValue* cv;
    pg = _piezoelectric_get_PointGroup(point_group);
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

            _piezoelectric_voigt_to_tensor(&value, index_string);
            cv[k].value = value;
            strcpy(cv[k].index, index_string);
            index_string[0] = '\0';
        }
    }

    // set dependent component

    n_material_generate_tensor(tensor, pg.unique, pg.relation, cv);
    free(cv);
}

void n_material_tensor_print_piezoelectric(double* tensor, const char* name) {
    int i = 0;
    ZF_LOGI(
        "---------Begin piezoelectric tensor in Voigt notation %s-------------",
        name);
    int row[6] = {0, 12, 24};
    for (i = 0; i < 3; i++) {
        ZF_LOGI("%i1=%10.3le %i2=%10.3le %i3=%10.3le %i4=%10.3le %i5=%10.3le % "
                "i6 = % 10.3le ",
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
        "--------- End piezoelectric tensor in Voigt notation %s -------------",
        name);
}

void n_material_tensor_print_file_piezoelectric(const char* name,
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