#include <effprop/effprop.h>

int nx = 100;
int ny = 1;
int nz = 100;
double dx = 1e-7;
double dy = 1e-7;
double dz = 1e-7;
int dim[3] = {100, 1, 100};
int phase_count = 1;
short* phase;
double delta[3] = {1e-7, 1e-7, 1e-7};
NFFTPtr nfft;
int output_frequency = 100;
char output_format[NAME_STRING] = "vti";
char system_type[NAME_STRING] = "dielectric";
double* zero;
double* tmp;
double* tmp1;
int t2v[3][3] = {
    {0, 5, 4},
    {5, 1, 3},
    {4, 3, 2}}; // this is the map to convert 2nd rank tensor to voigt
int iter_max = 500;
double iter_error = 1e-4;
double iter_step = 0.2;
int distribution = 0;

// dielectric
int control_dielectric = 0;
NPoissonSolverPtr eps; // electric poisson solver
double* permittivity;
double permittivity_homo[3][3] = {0};
double permittivity_effective[3][3] = {0};
double external_electric_field[3] = {0, 0, 2e8};
char external_electric_field_type[NAME_STRING] = "constant";
double* electric_potential;
double* electric_field;
double* energy_dielectric;
double* spontaneous_polarization;
double* polarization;
double* electric_displacement;
double* charge;
double* dielectric_rhs;
char control_input_spontaneous_polarization[NAME_STRING] = "";
char control_input_charge[NAME_STRING] = "";
double electric_displacement_avg[3] = {0};
double electric_displacement_avg_prev[3] = {0};

// electrical
NPoissonSolverPtr cps; // conndcutivity poisson solver
int control_electrical = 0;
double electrical_conductivity_homo[3][3] = {0};
double electrical_conductivity_effective[3][3] = {0};
double* electrical_conductivity;
double* electric_potential;
double* electric_field;
double* electrical_current;
double* energy_electrical;
double electrical_current_avg[3] = {0};

// diffusion
int control_diffusion = 0;
NPoissonSolverPtr dps; // diffusion poisson solver
double diffusivity_homo[3][3] = {0};
double diffusivity_effective[3][3] = {0};
double external_concentration_gradient[3] = {0, 0, 2e8};
double* diffusivity;
double* concentration;
double* concentration_gradient;
double* molar_flux;
double* energy_diffusion;
char external_concentration_gradient_type[NAME_STRING] = "constant";
double molar_flux_avg[3] = {0};

// elastic
int control_elastic = 0;
NElasticSolverPtr ems; // elastic mechanical solver
double stiffness_homo[3][3][3][3] = {0};
double stiffness_effective[3][3][3][3] = {0};
double external_strain[3][3] = {0};
double external_stress[3][3] = {0};
char external_elastic_type[NAME_STRING] = "stress";
int control_output_stress = 0;
int control_output_strain = 0;
double* stiffness;
double* strain;
double* eigenstrain;
double* stress;
double* displacement;
double* energy_elastic;
double stress_avg[3][3] = {0};
double stress_avg_prev[3][3] = {0};
double strain_avg[3][3] = {0};
double strain_avg_prev[3][3] = {0};

// thermal
int control_thermal = 0;
NPoissonSolverPtr tps; // thermal conductionn poisson solver
double thermal_conductivity_homo[3][3] = {0};
double heat_flux_avg[3] = {0};
double thermal_conductivity_effective[3][3] = {0};
double external_temperature_gradient[3] = {0, 0, 2e8};
double* thermal_conductivity;
double* temperature;
double* temperature_gradient;
double* heat_flux;
double* energy_thermal;
char external_temperature_gradient_type[NAME_STRING] = "constant";

// magnetic
int control_magnetic = 0;
NPoissonSolverPtr mps;
double* permeability;
double* magnetic_potential;
double* magnetic_field;
double* magnetic_induction;
double magnetic_induction_avg[3] = {0};
double magnetic_induction_avg_prev[3] = {0};
double* magnetization;
double* magnetic_rhs;
double permeability_homo[3][3] = {0};
double permeability_effective[3][3] = {0};
double* energy_magnetic;
double external_magnetic_field[3] = {0, 0, 2e8};
char external_magnetic_field_type[NAME_STRING] = "constant";

// piezoelectric
int control_piezoelectric = 0;
double* piezoelectric;
double piezoelectric_effective[3][3][3] = {0};

// piezomagnetic
int control_piezomagnetic = 0;
double* piezomagnetic;
double piezomagnetic_effective[3][3][3] = {0};

// magnetoelectric
int control_magnetoelectric = 0;
double* magnetoelectric;
double magnetoelectric_effective[3][3] = {0};
