#include <ntextutils/ntextutils.h>
#include <nmathfft/nmathfft.h>
#include <effprop/exports.h>
#include <effprop/errors.h>

// they are defined in the globalVariables.c
extern NPoissonSolverPtr dps;
extern double *diffusivity;
extern double *concentration;
extern double *concentration_gradient;
extern double *mol_flux;
extern double diffusivity_homo[3][3];
extern double *energy_diffusion;
extern double external_concentration_gradient[3];
extern char external_concentration_gradient_type[NAME_STRING];
extern int control_diffusion;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_diffusion();