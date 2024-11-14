

#ifndef __SUANEFFPROP_H__
#define __SUANEFFPROP_H__

// Include from std C library
#include "stdlib.h"
#if defined(_MSC_VER)
#else
#include <unistd.h>
#endif

// Include from other library
#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <ntextutils/ntextutils.h>

// Include of library developed by Nibiru
// #include <effprop/dielectric_electrical.h>
// #include <effprop/elastic.h>
// #include <effprop/diffusion.h>
// #include <effprop/thermal.h>

#include <effprop/errors.h>
#include <effprop/exports.h>
#include <nmaterialgenerator/material.h>
#include <nmathbasic/nmathbasic.h>
#include <nmathfft/nmathfft.h>
#include <nstructuregenerator/structuregenerator.h>

#ifdef __cplusplus
extern "C" {
#endif

extern NFFTPtr nfft;
extern short* phase;
extern double* zero;
extern double* tmp;
extern double* tmp1;
extern int nx, ny, nz;
extern double dx, dy, dz;
extern int dim[3];
extern double delta[3];
extern int phase_count;
extern int iter_max;
extern double iter_error;
extern char system_type[NAME_STRING];
// following are control variables
extern int control_output_format;
extern int output_frequency;
extern char output_format[NAME_STRING];
extern int distribution;

// dielectric and electrical
extern NPoissonSolverPtr eps;
extern double* electric_potential;
extern double* electric_field;
extern double* energy_dielectric;
extern double* energy_electrical;
extern char external_electric_field_type[NAME_STRING];
extern char control_input_spontaneous_polarization[NAME_STRING];
extern char control_input_charge[NAME_STRING];
extern double electric_displacement_avg[3];
extern double electric_displacement_avg_prev[3];

extern int control_dielectric;
extern double* permittivity;
extern double permittivity_homo[3][3];
extern double permittivity_effective[3][3];
extern double* spontaneous_polarization;
extern double* polarization;
extern double* electric_displacement;
extern double* dielectric_rhs;
extern double* charge;

extern double iter_step;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input();

// extern double *electric_displacement;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_dielectric_solver();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_dielectric_control();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
load_input_dielectric_boundary_condition();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_dielectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_dielectric_displacement();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_dielectric_polarization();
SUANEFFPROPPUBFUN int SUANEFFPROPCALL calculate_dielectric_convergence();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_dielectric_rhs_reset();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_dielectric_rhs_add_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_dielectric_rhs_add_magnetoelectric();

extern int control_electrical;
extern NPoissonSolverPtr cps; // conductivity poisson
extern double* electrical_conductivity;
extern double* electrical_current;
extern double electrical_conductivity_homo[3][3];
extern double electrical_conductivity_effective[3][3];
extern double external_electric_field[3];
extern double electrical_current_avg[3];
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_electrical();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_electrical_current();

// diffusion
extern int control_diffusion;
extern NPoissonSolverPtr dps;
extern double* diffusivity;
extern double* concentration;
extern double* concentration_gradient;
extern double* molar_flux;
extern double molar_flux_avg[3];
extern double diffusivity_homo[3][3];
extern double diffusivity_effective[3][3];
extern double* energy_diffusion;
extern double external_concentration_gradient[3];
extern char external_concentration_gradient_type[NAME_STRING];
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_diffusion();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_diffusion_molar_flux();

// elastic
extern int control_elastic;
extern NElasticSolverPtr ems; // elastic mechanical solver
extern double stiffness_homo[3][3][3][3];
extern double stiffness_effective[3][3][3][3];
extern double external_strain[3][3];
extern double external_stress[3][3];
extern char external_elastic_type[NAME_STRING];
extern int control_output_stress;
extern int control_output_strain;
extern double* stiffness;
extern double* strain;
extern double* eigenstrain;
extern double* stress;
extern double* displacement;
extern double* energy_elastic;
extern double stress_avg[3][3];
extern double strain_avg[3][3];
extern double stress_avg_prev[3][3];
extern double strain_avg_prev[3][3];
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_elastic_solver();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_elastic_control();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_elastic_boundary_condition();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_elastic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_elastic();
SUANEFFPROPPUBFUN int SUANEFFPROPCALL calculate_elastic_convergence();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_elastic_eigenstrain_reset();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_elastic_eigenstrain_add_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_elastic_eigenstrain_add_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_elastic_stress_strain_avg();

// thermal
extern NPoissonSolverPtr tps;
extern double* thermal_conductivity;
extern double* temperature;
extern double* temperature_gradient;
extern double* heat_flux;
extern double thermal_conductivity_homo[3][3];
extern double thermal_conductivity_effective[3][3];
extern double* energy_thermal;
extern double external_temperature_gradient[3];
extern double heat_flux_avg[3];
extern char external_temperature_gradient_type[NAME_STRING];
extern int control_thermal;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_thermal();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_thermal_heat_flux();

// magnetic
extern NPoissonSolverPtr mps;
extern double* permeability;
extern double* magnetic_potential;
extern double* magnetic_induction;
extern double magnetic_induction_avg[3];
extern double magnetic_induction_avg_prev[3];
extern double* magnetic_field;
extern double* magnetization;
extern double* magnetic_rhs;
extern double permeability_homo[3][3];
extern double permeability_effective[3][3];
extern double* energy_magnetic;
extern double external_magnetic_field[3];
extern char external_magnetic_field_type[NAME_STRING];
extern int control_magnetic;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_magnetic_solver();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_magnetic_control();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_magnetic_boundary_condition();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_magnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_magnetic_rhs_reset();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL calculate_magnetic_induction();
SUANEFFPROPPUBFUN int SUANEFFPROPCALL calculate_magnetic_convergence();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_magnetic_rhs_add_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
calculate_magnetic_rhs_add_magnetoelectric();

// piezoelectric
extern double* piezoelectric;
extern double piezoelectric_effective[3][3][3];
extern int control_piezoelectric;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
output_effective_property_piezoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_piezoelectric();

// piezomagnetic
extern double* piezomagnetic;
extern double piezomagnetic_effective[3][3][3];
extern int control_piezomagnetic;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
output_effective_property_piezomagnetic();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_piezomagnetic();

// magnetoelectric
extern double* magnetoelectric;
extern double magnetoelectric_effective[3][3];
extern int control_magnetoelectric;
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_solve_distribution_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
solve_effective_property_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL
output_effective_property_magnetoelectric();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_magnetoelectric();

/**
 * Class:
 * Description:
 * Parameters:
 * Methods:
 */
// typedef struct {
//     int x;
//     int y;
//     int z;
//     double *data;
// } NTemplate;
// typedef NTemplate* NTemplatePtr;

// SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_initialize();
// SUANEFFPROPPUBFUN void SUANEFFPROPCALL post_initialize();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_fft();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL initialize_structure();

// SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_destruct();
// SUANEFFPROPPUBFUN void SUANEFFPROPCALL post_destruct();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_fft();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL destruct_structure();

// SUANEFFPROPPUBFUN void SUANEFFPROPCALL pre_load_input();
// SUANEFFPROPPUBFUN void SUANEFFPROPCALL post_load_input();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_dimension();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL load_input_control();

SUANEFFPROPPUBFUN void SUANEFFPROPCALL normalize();

SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_distribution();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL output_effective_property();

SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_distribution();
SUANEFFPROPPUBFUN void SUANEFFPROPCALL solve_effective_property();

SUANEFFPROPPUBFUN void SUANEFFPROPCALL effective_property();

// SUANEFFPROPPUBFUN void SUANEFFPROPCALL get_nth_component(double *out,
// double *in, int total, int rank, int nth);

#ifdef __cplusplus
}
#endif

#endif /*__CONTROLFILE_H__*/
