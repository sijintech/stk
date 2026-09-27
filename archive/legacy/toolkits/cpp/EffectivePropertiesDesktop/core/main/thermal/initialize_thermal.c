#include <effprop/effprop.h>

void initialize_thermal()
{

    tps = calloc(1, sizeof(NPoissonSolver));
    thermal_conductivity = calloc(phase_count * 9, sizeof(double));
    temperature_gradient = calloc(nx * ny * nz * 3, sizeof(double));
    heat_flux = calloc(nx * ny * nz * 3, sizeof(double));
    temperature = calloc(nx * ny * nz, sizeof(double));
    energy_thermal = calloc(nx * ny * nz, sizeof(double));
    n_material_generator(thermal_conductivity, "input.xml", "/input/system/material", "thermal_conductivity");

    // n_material_tensor_distribution_print("thermal_conductivity", nx, ny, nz, phase, 2, thermal_conductivity, "11");
    n_fft_poisson_int_set(tps, "poisson_3d/phase_count", phase_count);
    n_fft_poisson_init(tps, nfft);
    n_fft_poisson_int_set(tps, "poisson_3d/control/rhs_source_nonzero", 0);
    n_fft_poisson_double_array_set(tps, "poisson_3d/epsilon_homo", NARR2PTR(double, thermal_conductivity_homo));
    n_material_tensor_print(NARR2PTR(double,thermal_conductivity_homo), 2, "Homogeneous thermal conductivity");
    n_fft_poisson_double_array_set(tps, "poisson_3d/external_field", external_temperature_gradient);
    n_fft_poisson_short_array_link(tps, "poisson_3d/phase", phase);
    n_fft_poisson_double_array_link(tps, "poisson_3d/epsilon", thermal_conductivity);
    n_fft_poisson_double_array_link(tps, "poisson_3d/potential", temperature);
    n_fft_poisson_double_array_link(tps, "poisson_3d/field", temperature_gradient);
    n_fft_poisson_double_array_link(tps, "poisson_3d/energy", energy_thermal);
    n_fft_poisson_double_array_link(tps, "poisson_3d/rhs_source", zero);
    n_fft_poisson_string_set(tps,"poisson_3d/solver_name","thermal");

    n_fft_poisson_setup(tps);
}

void destruct_thermal()
{
    free(thermal_conductivity);
    free(temperature_gradient);
    free(temperature);
    free(heat_flux);
    free(energy_thermal);
    n_fft_poisson_free(tps);
}
