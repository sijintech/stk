#include <nmathfft/nmathfft.h>

int main()
{
    int x = 3, y = 3, z = 3;
    int dim[3] = {x, y, z};
    int kdim[3] = {0};
    double delta[3] = {0.1, 0.1, 0.1};

    double stiffness[3][3][3][3] = {0.1, 0.1, 0.1};
    double(*strain)[x][y][z][6];
    double(*stress)[x][y][z][6];
    double(*strain_eigen)[x][y][z][6];
    short(*phase)[x][y][z];
    double(*zero)[x][y][z];
    double stiffness_homo[3][3][3][3]={0};

    NElasticSolverPtr psp;

    n_data_3D_double_init(x, y, z, &phase);
    n_data_3D_double_init(x, y, z, &zero);
    n_data_4D_double_init(x, y, z, 6, &stress);
    n_data_4D_double_init(x, y, z, 6, &strain);

    NFFT nfft;
    n_fft_data_set(&nfft,"r2c_3d/size", &(dim[0]));
    n_fft_data_set(&nfft,"r2c_3d/delta", &(delta[0]));
    n_fft_setup(&nfft,"r2c_3d");

    double epsilon_homo[6] = {20, 20, 20, 0, 0, 0};
    double external_field[3] = {0, 0, 1e6};

    n_fft_elastic_double_array_set(psp,"elastic_3d/stiffness_homo", stiffness_homo);
    n_fft_poisson_double_array_set(psp,"elastic_3d/external_field", external_field);


    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon23_delta", zero);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon13_delta", zero);
    n_fft_poisson_double_array_link(psp,"poisson_3d/epsilon12_delta", zero);

    n_fft_poisson_double_array_link(psp,"poisson_3d/potential", *potential);
    n_fft_poisson_double_array_link(psp,"poisson_3d/field", *field);
    n_fft_poisson_short_array_link(psp,"elastic_3d/phase", *phase);

    n_fft_elastic_init(psp,&nfft);
    n_fft_elastic_setup(psp);
    n_fft_elastic_solve_inhomo_rspace(psp);
    return 0;
}