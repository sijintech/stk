#include <ntextutils/ntextutils.h>
#include <nmathfft/nmathfft.h>
#include <effprop/exports.h>
#include <effprop/errors.h>

// they are defined in the globalVariables.c
extern NPoissonSolverPtr tps;
// following variables needs to be allocated after knowledge of the system size and phase count

// dielectric solver related
extern double *thermal_conductivity;
extern double *temperature;
extern double *temperature_gradient;
extern double *heat_flux;
extern double thermal_conductivity_homo[3][3];
extern double *energy_thermal;
extern double external_temperature_gradient[3];
extern char external_temperature_gradient_type[NAME_STRING];
extern int control_thermal;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_thermal();