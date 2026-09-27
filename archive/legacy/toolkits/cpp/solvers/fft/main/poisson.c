#include <nmathfft/nmathfft.h>

int main()
{
    int x = 3, y = 3, z = 3;
    int dim[3] = {x, y, z};
    int kdim[3] = {0};
    double delta[3] = {0.1, 0.1, 0.1};
    double(*potential)[x][y][z];
    double(*field)[x][y][z][3];
    double(*epsilon_delta_diagonal)[x][y][z];
    double(*zero)[x][y][z];

    NPoissonSolverPtr psp;

    n_data_3D_double_init(x, y, z, &epsilon_delta_diagonal);
    n_data_3D_double_init(x, y, z, &zero);
    n_data_3D_double_init(x, y, z, &potential);
    n_data_4D_double_init(x, y, z, 3, &field);

    // n_data_3D_double_fill(x, y, z, *epsilon_delta_diagonal);
    for (size_t i = 0; i < x; i++)
    {
        for (size_t j = 0; j < y; j++)
        {
            for (size_t k = 0; k < 2; k++)
            {
                (*epsilon_delta_diagonal)[i][j][k] = - (double)(k+1)*10;
                (*epsilon_delta_diagonal)[i][j][z - 1 - k] = - (double)(k+1) * 10;
            }
        }
    }
    NFFT nfft;
    n_fft_data_set(&nfft,"r2c_3d/size", &(dim[0]));
    n_fft_data_set(&nfft,"r2c_3d/delta", &(delta[0]));
    n_fft_setup(&nfft,"r2c_3d");

    double epsilon_homo[6] = {20, 20, 20, 0, 0, 0};
    double external_field[3] = {0, 0, 1e6};
    n_fft_poisson_int_set(psp,"poisson_3d/control/rhs_source_nonzero", 0);
    int temp = n_fft_poisson_int_get(psp,"poisson_3d/control/rhs_source_nonzero");
    ZF_LOGI("rhs source is nonzero %i", temp);
    n_fft_poisson_double_array_set(psp,"poisson_3d/epsilon_homo", epsilon_homo);
    ZF_LOGI("the homo epislon %f", epsilon_homo[3]);
    n_fft_poisson_double_array_set(psp,"poisson_3d/external_field", external_field);

    ZF_LOGI("The address for epsilon %p %p %e", epsilon_delta_diagonal, epsilon_delta_diagonal, (*epsilon_delta_diagonal)[1][1][1]);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon11_delta", epsilon_delta_diagonal);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon22_delta", epsilon_delta_diagonal);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon33_delta", epsilon_delta_diagonal);

    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon23_delta", zero);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon13_delta", zero);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon12_delta", zero);

    n_fft_poisson_double_array_link(psp,"poisson_3d/potential", *potential);
    n_fft_poisson_double_array_link(psp,"poisson_3d/field", *field);
    n_fft_poisson_double_array_link(psp,"poisson_3d/rhs_source", *zero);

    n_fft_poisson_init(psp,&nfft);

    n_fft_poisson_solve_inhomo_rspace(psp);
    return 0;
}