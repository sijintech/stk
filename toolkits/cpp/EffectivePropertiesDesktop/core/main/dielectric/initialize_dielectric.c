#include <effprop/effprop.h>

void initialize_dielectric()
{
    size_t i=0;
    eps = calloc(1, sizeof(NPoissonSolver));
    permittivity = calloc(phase_count * 9, sizeof(double));
    electric_field = calloc(nx * ny * nz * 3, sizeof(double));
    electric_potential = calloc(nx * ny * nz, sizeof(double));
    energy_dielectric = calloc(nx * ny * nz, sizeof(double));
    dielectric_rhs = calloc(nx * ny * nz, sizeof(double));
    spontaneous_polarization = calloc(nx * ny * nz * 3, sizeof(double));
    polarization = calloc(nx * ny * nz * 3, sizeof(double));
    electric_displacement = calloc(nx * ny * nz * 3, sizeof(double));
    charge = calloc(nx * ny * nz, sizeof(double));
    n_material_generator(permittivity, "input.xml", "/input/system/material", "permittivity");
    for (i = 0; i < 9*phase_count; i++)
    {
        permittivity[i] = permittivity[i]*NEPSILON0;
    }
    
    // n_material_tensor_distribution_print("permittivity", nx, ny, nz, phase, 2, permittivity, "11");
    n_fft_poisson_int_set(eps, "poisson_3d/phase_count", phase_count);
    n_fft_poisson_init(eps, nfft);
    n_fft_poisson_int_set(eps, "poisson_3d/control/rhs_source_nonzero", 0);
    n_fft_poisson_int_set(eps,"poisson_3d/control/max_iterations",500);
    n_fft_poisson_double_set(eps,"poisson_3d/control/threshold",1e-5);
    n_fft_poisson_double_array_set(eps, "poisson_3d/epsilon_homo", NARR2PTR(double,permittivity_homo));
    n_material_tensor_print(NARR2PTR(double,permittivity_homo), 2, "Homogeneous permittivity");
    n_fft_poisson_double_array_set(eps, "poisson_3d/external_field", external_electric_field);
    // ZF_LOGI("external field %f", external_electric_field[2]);
    n_fft_poisson_short_array_link(eps, "poisson_3d/phase", phase);
    n_fft_poisson_double_array_link(eps, "poisson_3d/epsilon", permittivity);
    n_fft_poisson_double_array_link(eps, "poisson_3d/potential", electric_potential);
    n_fft_poisson_double_array_link(eps, "poisson_3d/field", electric_field);
    n_fft_poisson_double_array_link(eps, "poisson_3d/energy", energy_dielectric);
    n_fft_poisson_double_array_link(eps, "poisson_3d/rhs_source", dielectric_rhs);
    n_fft_poisson_string_set(eps,"poisson_3d/solver_name","dielectric");
    n_fft_poisson_setup(eps);

    if (control_input_spontaneous_polarization[0]!='\0')
        n_vtiFile_4D_double_read(nx,ny,nz,3, NPTR2ARR4D(double,spontaneous_polarization,nx,ny,nz,3), control_input_spontaneous_polarization);
    if (control_input_charge[0]!='\0')
        n_vtiFile_3D_double_read(nx,ny,nz, NPTR2ARR3D(double,charge,nx,ny,nz), control_input_charge);


    calculate_dielectric_rhs_reset();
    // // now prepare the rhs;
    // const char derivative_name[3][10] = {"r2c_3d/x", "r2c_3d/y", "r2c_3d/z"};
    // //prepare the rhs
    // for (size_t i = 0; i < eps->rspace_totalsize; i++)
    // {
    //     dielectric_rhs[i] = charge[i]/NEPSILON0;
    // }

    // for (size_t m = 0; m < 3; m++)
    // {
    //     n_data_double_get_nth_component(eps->rspace_totalsize, 3, m, tmp, spontaneous_polarization);
    //     n_fft_r2c_derivative(nfft, derivative_name[m], tmp, tmp1);
    //     for (size_t i = 0; i < eps->rspace_totalsize; i++)
    //     {
    //         dielectric_rhs[i] = dielectric_rhs[i] - tmp1[i]/NEPSILON0;
    //     }
    // }
}

void destruct_dielectric()
{
    free(permittivity);
    free(electric_field);
    free(electric_potential);
    free(energy_dielectric);
    free(dielectric_rhs);
    free(spontaneous_polarization);
    free(polarization);
    free(electric_displacement);
    free(charge);
    n_fft_poisson_free(eps);
}
