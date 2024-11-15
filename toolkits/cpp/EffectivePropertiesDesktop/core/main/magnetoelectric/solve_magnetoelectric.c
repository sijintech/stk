#include <effprop/effprop.h>

void pre_solve_distribution_magnetoelectric()
{
    pre_solve_distribution_elastic();
    pre_solve_distribution_dielectric();
    pre_solve_distribution_magnetic();
}

void post_solve_magnetoelectric()
{
}

void solve_distribution_magnetoelectric()
{
    size_t iter=0;

    for (iter = 0; iter < iter_max; iter++)
    {
        calculate_elastic_eigenstrain_reset();
        calculate_elastic_eigenstrain_add_piezoelectric();
        calculate_elastic_eigenstrain_add_piezomagnetic();
        solve_distribution_elastic();

        calculate_dielectric_rhs_reset();
        calculate_dielectric_rhs_add_piezoelectric();
        calculate_dielectric_rhs_add_magnetoelectric();
        solve_distribution_dielectric();

        calculate_magnetic_rhs_reset();
        // prepare the spontaneous p and rhs for poisson
        calculate_magnetic_rhs_add_piezomagnetic();
        calculate_magnetic_rhs_add_magnetoelectric();
        solve_distribution_magnetic();


        if (calculate_magnetic_convergence() == 1 && calculate_elastic_convergence() == 1 && calculate_magnetic_convergence() == 1)
        {
            break;
        }
    }
}

void solve_effective_property_magnetoelectric()
{
    size_t m=0;
    size_t n=0;
    size_t i=0;
    size_t j=0;

    n_fft_elastic_reset(ems);
    calculate_elastic_eigenstrain_reset();
    // calculate_elastic_eigenstrain_add_piezoelectric();
    solve_effective_property_elastic();

    n_fft_poisson_reset(eps);
    calculate_dielectric_rhs_reset();
    // calculate_dielectric_rhs_add_piezoelectric();
    solve_effective_property_dielectric();

    n_fft_poisson_reset(mps);
    calculate_magnetic_rhs_reset();
    // calculate_dielectric_rhs_add_piezoelectric();
    solve_effective_property_magnetic();

    char solvername[128] = "";
    char direction[3][5] = {"x", "y", "z"};

    strcpy(external_elastic_type, "stress");
    n_fft_elastic_int_set(ems, "elastic_3d/control/constrain_type", 1); // 0 is the strain constraint
    // elastic reset
    for (m = 0; m < 3; m++)
    {
        for (n = 0; n < 3; n++)
        {
            external_stress[m][n] = 0;
            external_strain[m][n] = 0;
        }
    }
    n_fft_elastic_double_array_set(ems, "elastic_3d/stress_avg", NARR2PTR(double,external_stress));
    n_fft_elastic_double_array_set(ems, "elastic_3d/strain_avg", NARR2PTR(double,external_strain));

    for (i = 0; i < 3; i++)
    {
        n_fft_elastic_reset(ems);
        n_fft_poisson_reset(eps);
        n_fft_poisson_reset(mps);
        external_electric_field[0] = 0;
        external_electric_field[1] = 0;
        external_electric_field[2] = 0;
        external_electric_field[i] = 0.001;
        n_fft_poisson_double_array_set(eps, "poisson_3d/external_field", external_electric_field);
        n_string_join(solvername, "magnetoelectric_solve_field", direction[i], "_");
        n_fft_poisson_string_set(eps, "poisson_3d/solver_name", solvername);

        solve_distribution_magnetoelectric();

        for (j = 0; j < 3; j++)
        {

            magnetoelectric_effective[i][j] = magnetic_induction_avg[j] / external_electric_field[i];
        }
    }
}