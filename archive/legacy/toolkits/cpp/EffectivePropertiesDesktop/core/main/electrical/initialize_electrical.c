#include <effprop/effprop.h>

void initialize_electrical()
{

    cps = calloc(1, sizeof(NPoissonSolver));
    electrical_conductivity = calloc(phase_count * 9, sizeof(double));
    electrical_current = calloc(nx * ny * nz * 3, sizeof(double));
    electric_field = calloc(nx * ny * nz * 3, sizeof(double));
    electric_potential = calloc(nx * ny * nz, sizeof(double));
    energy_electrical = calloc(nx * ny * nz, sizeof(double));
    n_material_generator(electrical_conductivity, "input.xml", "/input/system/material", "electrical_conductivity");
    // n_vtiFile_4D_double_write(nx, ny, nz, 3, NPTR2ARR4D(double,electrical_conductivity,nx, ny, nz, 9), "electrical_conductivity_check.vti");

    // n_material_tensor_distribution_print("diffusivity", nx, ny, nz, phase, 2, diffusivity, "11");
    n_fft_poisson_int_set(cps, "poisson_3d/phase_count", phase_count);
    n_fft_poisson_init(cps, nfft);
    n_fft_poisson_int_set(cps, "poisson_3d/control/rhs_source_nonzero", 0);
    n_fft_poisson_double_set(cps, "poisson_3d/control/iter_step", iter_step);
    n_fft_poisson_double_set(cps, "poisson_3d/control/threshold", iter_error);
    n_fft_poisson_double_array_set(cps, "poisson_3d/epsilon_homo", NARR2PTR(double,electrical_conductivity_homo));
    n_material_tensor_print(NARR2PTR(double,electrical_conductivity_homo), 2, "Homogeneous electrical conductivity");
    n_fft_poisson_double_array_set(cps, "poisson_3d/external_field", external_electric_field);
    n_fft_poisson_short_array_link(cps, "poisson_3d/phase", phase);
    n_fft_poisson_double_array_link(cps, "poisson_3d/epsilon", electrical_conductivity);
    n_fft_poisson_double_array_link(cps, "poisson_3d/potential", electric_potential);
    n_fft_poisson_double_array_link(cps, "poisson_3d/field", electric_field);
    n_fft_poisson_double_array_link(cps, "poisson_3d/rhs_source", zero);
    n_fft_poisson_double_array_link(cps, "poisson_3d/energy", energy_electrical);
    n_fft_poisson_string_set(cps,"poisson_3d/solver_name","electrical");
    n_fft_poisson_setup(cps);
}

void destruct_electrical()
{
    free(electrical_conductivity);
    free(electric_field);
    free(electrical_current);
    free(electric_potential);
    free(energy_electrical);
    n_fft_poisson_free(cps);
}
