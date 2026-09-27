#include "effprop/effprop.h"

void initialize_elastic() {
    ems = calloc(1, sizeof(NElasticSolver));
    stiffness = calloc(phase_count * 81, sizeof(double));
    stress = calloc(nx * ny * nz * 6, sizeof(double));
    strain = calloc(nx * ny * nz * 6, sizeof(double));
    eigenstrain = calloc(nx * ny * nz * 6, sizeof(double));
    displacement = calloc(nx * ny * nz * 3, sizeof(double));
    energy_elastic = calloc(nx * ny * nz, sizeof(double));
    n_material_generator(
        stiffness, "input.xml", "/input/system/material", "stiffness");

    // n_material_tensor_distribution_print("stiffness", nx, ny, nz, phase, 4,
    //                                      stiffness, "1111");

    n_fft_elastic_int_set(ems, "elastic_3d/phase_count", phase_count);
    n_fft_elastic_init(ems, nfft);
    n_fft_elastic_double_array_set(
        ems, "elastic_3d/stiffness_homo", NARR2PTR(double, stiffness_homo));
    n_material_tensor_print_stiffness(NARR2PTR(double, stiffness_homo),
                                      "Homogeneous stiffness");
    int choice = 0;
    if (strcmp(external_elastic_type, "strain") == 0) {
        choice = 0;
    } else {
        choice = 1;
    }
    n_fft_elastic_int_set(ems, "elastic_3d/control/constrain_type", choice);
    if (choice == 0) {
        n_fft_elastic_double_array_set(
            ems, "elastic_3d/strain_avg", NARR2PTR(double, external_strain));
    } else {
        n_fft_elastic_double_array_set(
            ems, "elastic_3d/stress_avg", NARR2PTR(double, external_stress));
    }
    n_fft_elastic_short_array_link(ems, "elastic_3d/phase", phase);
    n_fft_elastic_double_array_link(ems, "elastic_3d/stiffness", stiffness);
    n_fft_elastic_double_array_link(ems, "elastic_3d/stress", stress);
    n_fft_elastic_double_array_link(ems, "elastic_3d/strain", strain);
    n_fft_elastic_double_array_link(
        ems, "elastic_3d/displacement", displacement);
    n_fft_elastic_double_array_link(
        ems, "elastic_3d/strain_eigen", eigenstrain);
    n_fft_elastic_double_array_link(ems, "elastic_3d/energy", energy_elastic);
    n_fft_elastic_string_set(ems, "poisson_3d/solver_name", "elastic");
    n_fft_elastic_setup(ems);

    // for (int k = 0; k < phase_count * 81; k++)
    // {
    //     ZF_LOGI("stiffness0  %i %f", k, stiffness[k]);
    // }

    calculate_elastic_eigenstrain_reset();
}

void destruct_elastic() {
    free(stiffness);
    free(stress);
    free(strain);
    free(eigenstrain);
    free(displacement);
    n_fft_elastic_free(ems);
}
