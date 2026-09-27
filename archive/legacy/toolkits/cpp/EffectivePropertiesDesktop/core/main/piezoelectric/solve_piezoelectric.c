#include <effprop/effprop.h>

void pre_solve_distribution_piezoelectric()
{
    pre_solve_distribution_elastic();
    pre_solve_distribution_dielectric();
}

void post_solve_piezoelectric()
{
}

void solve_distribution_piezoelectric()
{
    size_t iter=0;

    for (iter = 0; iter < iter_max; iter++)
    {
        calculate_elastic_eigenstrain_reset();
        calculate_elastic_eigenstrain_add_piezoelectric();
        solve_distribution_elastic();

        calculate_dielectric_rhs_reset();
        calculate_dielectric_rhs_add_piezoelectric();
        solve_distribution_dielectric();



        if (calculate_dielectric_convergence() == 1 && calculate_elastic_convergence() == 1 && iter>0)
        {
            break;
        }
    }
}

void solve_effective_property_piezoelectric()
{
    size_t i=0;
    size_t j=0;
    size_t k=0;
    size_t m=0;
    size_t n=0;

    n_fft_elastic_reset(ems);
    calculate_elastic_eigenstrain_reset();
    // calculate_elastic_eigenstrain_add_piezoelectric();
    solve_effective_property_elastic();

    n_fft_poisson_reset(eps);
    calculate_dielectric_rhs_reset();
    // calculate_dielectric_rhs_add_piezoelectric();
    solve_effective_property_dielectric();

    char solvername[128]="";
    char direction[3][5]={"x","y","z"};

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

    for (i = 0; i <3; i++)
    {
        n_fft_elastic_reset(ems);
        n_fft_poisson_reset(eps);
        external_electric_field[0] = 0;
        external_electric_field[1] = 0;
        external_electric_field[2] = 0;
        external_electric_field[i] = 0.001;
        // external_electric_field[i] = 112943.302462164;
        n_fft_poisson_double_array_set(eps, "poisson_3d/external_field", external_electric_field);
        n_string_join(solvername, "piezoelectric_solve_field", direction[i], "_");
        n_fft_poisson_string_set(eps,"poisson_3d/solver_name",solvername);

        solve_distribution_piezoelectric();

        for (j = 0; j < 3; j++)
        {
            for (k = 0; k < 3; k++)
            {
                piezoelectric_effective[i][j][k] = strain_avg[j][k] / external_electric_field[i];
            }
        }
    }
}
