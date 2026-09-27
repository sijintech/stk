#include <nmathfft/nmathfft.h>
#include <unity.h>

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

void test_n_poisson_prepare(){
    int size[3] = {nxx,nyy,nzz};
    int ksize[3] = {0, 0, 0};
    double delta[3] = {0.1, 0.2, 0.3};
    NFFT nfft;
    n_fft_data_set(&nfft,"r2c_3d/size", size);
    n_fft_data_set(&nfft,"r2c_3d/delta", delta);
    n_fft_setup(&nfft,"r2c_3d");
    ZF_LOGI("setup fft");
    TEST_ASSERT_EQUAL_FLOAT(1,1);

    NPoissonSolver psp;
    n_fft_poisson_init(&psp,&nfft);
}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_poisson_prepare);
    return UNITY_END();
}