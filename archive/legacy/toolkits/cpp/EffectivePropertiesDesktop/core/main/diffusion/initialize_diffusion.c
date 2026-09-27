#include <effprop/effprop.h>

void initialize_diffusion()
{

    dps = calloc(1, sizeof(NPoissonSolver));
    diffusivity = calloc(phase_count * 9, sizeof(double));
    concentration_gradient = calloc(nx * ny * nz * 3, sizeof(double));
    concentration = calloc(nx * ny * nz, sizeof(double));
    molar_flux = calloc(nx * ny * nz * 3, sizeof(double));
    energy_diffusion = calloc(nx * ny * nz, sizeof(double));
    // diffusion_rhs = calloc(nx * ny * nz, sizeof(double));

    n_material_generator(diffusivity, "input.xml", "/input/system/material", "diffusivity");

    // n_material_tensor_distribution_print("diffusivity", nx, ny, nz, phase, 2, diffusivity, "11");
    n_fft_poisson_int_set(dps, "poisson_3d/phase_count", phase_count);
    n_fft_poisson_init(dps, nfft);
    n_fft_poisson_int_set(dps, "poisson_3d/control/rhs_source_nonzero", 0);
    n_fft_poisson_double_array_set(dps, "poisson_3d/epsilon_homo", NARR2PTR(double,diffusivity_homo));
    n_material_tensor_print(NARR2PTR(double,diffusivity_homo), 2, "Homogeneous diffusivity");
    n_fft_poisson_double_array_set(dps, "poisson_3d/external_field", external_concentration_gradient);
    n_fft_poisson_short_array_link(dps, "poisson_3d/phase", phase);
    n_fft_poisson_double_array_link(dps, "poisson_3d/epsilon", diffusivity);
    n_fft_poisson_double_array_link(dps, "poisson_3d/potential", concentration);
    n_fft_poisson_double_array_link(dps, "poisson_3d/field", concentration_gradient);
    n_fft_poisson_double_array_link(dps, "poisson_3d/rhs_source", zero);
    n_fft_poisson_double_array_link(dps, "poisson_3d/energy", energy_diffusion);
    n_fft_poisson_string_set(dps,"poisson_3d/solver_name","diffusion");
    n_fft_poisson_setup(dps);

}

void destruct_diffusion()
{
    free(diffusivity);
    free(concentration_gradient);
    free(concentration);
    free(molar_flux);
    free(energy_diffusion);
    n_fft_poisson_free(dps);
}
