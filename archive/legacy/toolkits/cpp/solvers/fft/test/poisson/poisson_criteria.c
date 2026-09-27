#include <nmathfft/nmathfft.h>
#include <unity.h>
#include "fftw3.h"

#define nxx 15
#define nyy 5
#define nzz 2

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void test_n_poisson_criteria(){
    int size[3] = {nxx,nyy,nzz};
    int ksize[3] = {0, 0, 0};
    double delta[3] = {0.1, 0.2, 0.3};
    NFFT nfft;
    int rspacesize=0;
    n_fft_data_set(&nfft,"r2c_3d/size", size);
    n_fft_data_set(&nfft,"r2c_3d/delta", delta);
    n_fft_setup(&nfft, "r2c_3d");
    ZF_LOGI("setup fft");
    double(*in2)[nxx][nyy][nzz];
    // double *in;

    fftw_complex(*out)[nxx][nyy][nzz/2+1];
    n_data_3D_double_init(nxx, nyy, nzz, &in2);
    out = calloc(nxx*nyy*(nzz/2+1),sizeof(fftw_complex));

    n_fftw_r2c_3d_backward(&nfft,*out, *in2);

    int phase_count;
    phase_count = 2;
    double (*epsilon_delta)[phase_count][3][3];
    double (*potential)[nxx][nyy][nzz];
    double (*field)[nxx][nyy][nzz][3];
    double (*source)[nxx][nyy][nzz];
    double *temp;

    short (*phase)[nxx][nyy][nzz];
    n_data_3D_double_init(phase_count, 3, 3, &epsilon_delta);
    n_data_3D_double_init(nxx, nyy, nzz, &potential);
    n_data_3D_double_init(nxx, nyy, nzz, &source);
    n_data_4D_double_init(nxx, nyy, nzz, 3, &field);
    n_data_3D_short_init(nxx,nyy,nzz, &phase);

    NPoissonSolver psp;
    n_fft_poisson_init(&psp,&nfft);
    (*epsilon_delta)[0][0][0]=-0.3;
    (*epsilon_delta)[0][0][1]=1.1;
    // temp=epsilon_delta;
    // ZF_LOGI("pointerasdfasdf  %p %p %f %f ",epsilon_delta,*epsilon_delta, temp[0],(*epsilon_delta)[0][0][0]);
    // ZF_LOGI("pointerasdfasdf  %p %p %f %f ",epsilon_delta,*epsilon_delta, (*epsilon_delta)[0][0][0], (*epsilon_delta)[0][0][1]);
    n_fft_poisson_data_link(&psp,"poisson_3d/epsilon_delta",(double*)epsilon_delta);
    n_fft_poisson_data_link(&psp,"poisson_3d/potential",(double*)potential);
    n_fft_poisson_data_link(&psp,"poisson_3d/field",(double*)field);
    n_fft_poisson_data_link(&psp,"poisson_3d/rhs_source",(double*)source);

    // psp.poisson_3d_k_potential[1] = 1+I;




    ZF_LOGI("after setup");
    n_fft_poisson_check_ready(&psp);
    n_fft_poisson_calculate_error(&psp);
    int converge = n_fft_poisson_converge(&psp);
    ZF_LOGI("The error %f",psp.error);
    ZF_LOGI("Converge %i",converge);
    TEST_ASSERT_EQUAL_INT(converge,1);
}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_poisson_criteria);
    return UNITY_END();
}