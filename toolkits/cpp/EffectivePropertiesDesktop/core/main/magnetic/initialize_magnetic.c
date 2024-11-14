#include <effprop/effprop.h>

void initialize_magnetic()
{
    size_t i = 0;

    mps = calloc(1, sizeof(NPoissonSolver));
    permeability = calloc(phase_count * 9, sizeof(double));
    magnetic_field = calloc(nx * ny * nz * 3, sizeof(double));
    magnetic_potential = calloc(nx * ny * nz, sizeof(double));
    magnetization = calloc(nx * ny * nz * 3, sizeof(double));
    magnetic_rhs = calloc(nx * ny * nz, sizeof(double));
    energy_magnetic = calloc(nx * ny * nz, sizeof(double));
    magnetic_induction = calloc(nx * ny * nz * 3, sizeof(double));
    n_material_generator(permeability, "input.xml", "/input/system/material",
                         "permeability");
    for (i = 0; i < 9 * phase_count; i++)
    {
        permeability[i] = permeability[i] * NMU0;
    }

    // n_material_tensor_distribution_print("permeability", nx, ny, nz, phase,
    // 2, permeability, "11");
    n_fft_poisson_int_set(mps, "poisson_3d/phase_count", phase_count);
    n_fft_poisson_init(mps, nfft);
    n_fft_poisson_int_set(mps, "poisson_3d/control/rhs_source_nonzero", 0);
    n_fft_poisson_double_array_set(mps, "poisson_3d/epsilon_homo",
                                   NARR2PTR(double, permeability_homo));
    n_material_tensor_print(NARR2PTR(double, permeability_homo), 2,
                            "Homogeneous permeability");
    n_fft_poisson_double_array_set(mps, "poisson_3d/external_field",
                                   external_magnetic_field);
    n_fft_poisson_int_set(mps, "poisson_3d/control/max_iterations", 500);
    n_fft_poisson_double_set(mps, "poisson_3d/control/threshold", 1e-4);
    n_fft_poisson_short_array_link(mps, "poisson_3d/phase", phase);
    n_fft_poisson_double_array_link(mps, "poisson_3d/epsilon", permeability);
    n_fft_poisson_double_array_link(mps, "poisson_3d/potential",
                                    magnetic_potential);
    n_fft_poisson_double_array_link(mps, "poisson_3d/field", magnetic_field);
    n_fft_poisson_double_array_link(mps, "poisson_3d/energy", energy_magnetic);
    n_fft_poisson_double_array_link(mps, "poisson_3d/rhs_source", magnetic_rhs);
    n_fft_poisson_string_set(mps, "poisson_3d/solver_name", "magnetic");
    n_fft_poisson_setup(mps);

    calculate_magnetic_rhs_reset();
}

void destruct_magnetic()
{
    free(permeability);
    free(magnetic_field);
    free(magnetic_potential);
    free(magnetic_rhs);
    free(magnetization);
    free(magnetic_induction);
    free(energy_magnetic);
    n_fft_poisson_free(mps);
}
