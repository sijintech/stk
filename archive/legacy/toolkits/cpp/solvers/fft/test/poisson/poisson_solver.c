#include <nmathfft/nmathfft.h>
#include <unity.h>

#define nxx 10
#define nyy 10
#define nzz 10

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void test_n_poisson_solve(){
    int size[3] = {nxx,nyy,nzz};
    int ksize[3] = {0, 0, 0};
    double delta[3] = {0.1, 0.2, 0.3};
    NFFT nfft;
    int rspacesize=0;
    ZF_LOGI("Set up the fft");
    n_fft_data_set(&nfft,"r2c_3d/size", size);
    n_fft_data_set(&nfft,"r2c_3d/delta", delta);
    n_fft_setup(&nfft, "r2c_3d");

    ZF_LOGI("create the necessary data array");
    int phase_count;
    phase_count = 2;
    double (*epsilon_delta)[phase_count][3][3];
    double epsilon_homo[6]={0};
    double (*potential)[nxx][nyy][nzz];
    double (*field)[nxx][nyy][nzz][3];
    double (*source)[nxx][nyy][nzz];
    double external_field[3];
    short (*phase)[nxx][nyy][nzz];
    n_data_3D_double_init(phase_count, 3, 3, &epsilon_delta);
    n_data_3D_double_init(nxx, nyy, nzz, &potential);
    n_data_3D_double_init(nxx, nyy, nzz, &source);
    n_data_4D_double_init(nxx, nyy, nzz, 3, &field);
    n_data_3D_short_init(nxx,nyy,nzz, &phase);

    ZF_LOGI("set up the poisson solver");
    NPoissonSolver psp;
    n_fft_poisson_init(&psp,&nfft);
    n_fft_poisson_data_link(&psp,"poisson_3d/phase",(short*)phase);
    n_fft_poisson_data_link(&psp,"poisson_3d/epsilon_delta",(double*)epsilon_delta);
    n_fft_poisson_data_link(&psp,"poisson_3d/potential",(double*)potential);
    n_fft_poisson_data_link(&psp,"poisson_3d/field",(double*)field);
    n_fft_poisson_data_link(&psp,"poisson_3d/rhs_source",(double*)source);
    // assign values
    epsilon_homo[0]=1000;
    epsilon_homo[1]=1000;
    epsilon_homo[2]=1000;
    external_field[0]=0;
    external_field[1]=0;
    external_field[2]=1e5;
    (*phase)[2][2][2]=1;
    (*phase)[3][2][2]=1;
    (*phase)[2][3][2]=1;
    (*phase)[2][2][3]=1;
    (*epsilon_delta)[0][0][0] = -500;
    (*epsilon_delta)[0][1][1] = -500;
    (*epsilon_delta)[0][2][2] = -500;
    (*epsilon_delta)[1][0][0] = 0;
    (*epsilon_delta)[1][1][1] = 0;
    (*epsilon_delta)[1][2][2] = 0;
    n_fft_poisson_data_set(&psp,"poisson_3d/epsilon_homo",epsilon_homo);
    n_fft_poisson_setup(&psp);
    n_fft_poisson_data_set(&psp,"poisson_3d/phase_count",phase_count);
    n_fft_poisson_data_set(&psp,"poisson_3d/external_field",external_field);

    ZF_LOGI("Start the poisson solver");
    n_fft_poisson_solve_inhomo_rspace(&psp);

    ZF_LOGI("Check the final output data");


    TEST_ASSERT_EQUAL_INT(1,1);
}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_poisson_solve);
    return UNITY_END();
}