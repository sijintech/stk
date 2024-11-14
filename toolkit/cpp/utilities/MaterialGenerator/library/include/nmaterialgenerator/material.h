#ifndef __NMATERIAL_H__
#define __NMATERIAL_H__
#include "niobasic/niobasic.h"
#include "nmaterialgenerator/exports.h"
#include "ntextutils/ntextutils.h"
#include "zf_log.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct _PointGroup PointGroup;
typedef PointGroup* PointGroupPtr;
struct _PointGroup {
    int nonzero;
    int unique;
    int independent;
    NStringArray relation[81];
};

typedef struct _ComponentValue ComponentValue;
typedef ComponentValue* ComponentValuePtr;
struct _ComponentValue {
    double value;
    char index[10];
};

typedef struct _PGConstrain PGConstrain;
typedef PGConstrain* PGConstrainPtr;
struct _PGConstrain {
    int count;
    NStringArray constrain[4];
};

extern PointGroup PGRank4[32];
extern PGConstrain PGRank4Constrain[32];
NMATERIALGENERATORPUBFUN NStringArray NMATERIALGENERATORCALL
n_material_get_equivalent_index(int* sign,
                                const char* pg,
                                int rank,
                                const char* index);
NMATERIALGENERATORPUBFUN int NMATERIALGENERATORCALL
n_material_index_string_to_int(const char* equal_string);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_assign_by_index_string(double* tensor,
                                         const char* equal_string,
                                         double value);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print(double* tensor, int rank, const char* name);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_distribution_print(const char* name,
                                     int nx,
                                     int ny,
                                     int nz,
                                     short* eta,
                                     int rank,
                                     double* tensor,
                                     const char* index);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator(double* tensor,
                     const char* filename,
                     const char* xpath,
                     const char* tensorname);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_one_phase(double* tensor,
                               const char* filename,
                               const char* xpath,
                               const char* tensorname);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_f(double** tensor,
                       const char* filename,
                       const char* xpath,
                       const char* tensorname);
NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_one_phase_f(double** tensor,
                                 const char* filename,
                                 const char* xpath,
                                 const char* tensorname);
NMATERIALGENERATORPUBFUN int NMATERIALGENERATORCALL
n_material_get_point_group_from_string(const char* point_group);
NMATERIALGENERATORPUBFUN double NMATERIALGENERATORCALL
n_material_parse_expression(double* tensor, const char* expression);
NMATERIALGENERATORPUBFUN int NMATERIALGENERATORCALL n_material_get_tensor_rank(
    const char* filename, const char* xpathText, const char* tensorname);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generate_tensor(double* tensor,
                           int unique,
                           NStringArray pg[unique],
                           ComponentValue cv[unique]);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_one_tensor(double* tensor,
                                const char* filename,
                                const char* xpathText);

NMATERIALGENERATORPUBFUN double NMATERIALGENERATORCALL
_component_value_get(int n, ComponentValue cv[n], const char* index);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_tensor_general_rank0(double* tensor,
                                          const char* filename,
                                          const char* xpathText);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_tensor_rank2(double* tensor,
                                          const char* filename,
                                          const char* xpathText);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_tensor_stiffness(double* tensor,
                                      const char* filename,
                                      const char* xpathText);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_tensor_piezoelectric(double* tensor,
                                          const char* filename,
                                          const char* xpathText);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_generator_tensor_piezomagnetic(double* tensor,
                                          const char* filename,
                                          const char* xpathText);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_stiffness(double* tensor, const char* name);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_file_stiffness(const char* name, double* tensor);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_piezoelectric(double* tensor, const char* name);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_file_piezoelectric(const char* name, double* tensor);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_piezomagnetic(double* tensor, const char* name);

NMATERIALGENERATORPUBFUN void NMATERIALGENERATORCALL
n_material_tensor_print_file_piezomagnetic(const char* name, double* tensor);

#ifdef __cplusplus
}
#endif

#endif