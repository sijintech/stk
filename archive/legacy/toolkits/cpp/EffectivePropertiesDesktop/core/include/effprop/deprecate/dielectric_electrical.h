#include <ntextutils/ntextutils.h>
#include <nmathfft/nmathfft.h>
#include <effprop/exports.h>
#include <effprop/errors.h>

extern NPoissonSolverPtr eps;
extern double *electric_potential;
extern double *electric_field;
extern double *energy_dielectric;
extern double external_electric_field[3];
extern char external_electric_field_type[NAME_STRING];

extern int control_dielectric;
extern double *permittivity;
extern double *electric_displacement;
extern double permittivity_homo[3][3];
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_dielectric();

extern int control_electric;
extern double *electrical_conductivity;
extern double *electrical_current;
extern double electrical_conductivity_homo[3][3];
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_electrical();
