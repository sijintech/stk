#include <ntextutils/ntextutils.h>
#include <nmathfft/nmathfft.h>
#include <effprop/exports.h>
#include <effprop/errors.h>

extern int control_elastic;
extern NElasticSolverPtr ems; // elastic mechanical solver
extern double stiffness_homo[3][3][3][3];
extern double external_strain[3][3];
extern double external_stress[3][3];
extern char external_elastic_type[NAME_STRING];
extern int control_output_stress;
extern int control_output_strain;
extern double *stiffness;
extern double *strain;
extern double *eigenstrain;
extern double *stress;
extern double *displacement;
extern double *energy_elastic;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_elastic();
