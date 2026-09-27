#include <unity.h>
#include <zf_log.h>
#include "nmathfft/nmathfft.h"
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

    NFFT nfft;
void Test_n_fft_setup()
{
    int size[3] = {nxx,nyy,nzz};
    int ksize[3] = {0, 0, 0};
    double delta[3] = {0.1, 0.2, 0.3};
    n_fft_data_set(&nfft, "r2c_3d/size", size);
    n_fft_data_set(&nfft, "r2c_3d/delta", delta);
    n_fft_setup(&nfft, "r2c_3d");
    n_fft_data_get(&nfft, "r2c_3d/ksize", ksize);
    ZF_LOGD("The ksize is: %i, %i, %i",ksize[0],ksize[1],ksize[2]);

    double (*kvec)[ksize[0]][ksize[1]][ksize[2]][3];
    double **temp;
    // double *temp;
    // n_data_4D_double_init(ksize[0],ksize[1],ksize[2],3, &kvec);
    // temp = malloc(ksize[0]*ksize[1]*ksize[2]*sizeof(double));
    temp=&kvec;
    n_fft_data_link(&nfft,"r2c_3d/kvector", (double **)&kvec);
    // memcpy(*kx,temp,ksize[0]*ksize[1]*ksize[2]*sizeof(double));
    ZF_LOGD("The kx is: %f, %f, %f, %f",(*kvec)[0][0][0][0],(*kvec)[1][0][0][0],(*kvec)[2][0][0][0],(*kvec)[3][0][0][0]);
    TEST_ASSERT_EQUAL_INT(ksize[2], nzz/2+1);
    TEST_ASSERT_EQUAL_FLOAT((*kvec)[2][0][0][0], 2 * NPI * 2 / 0.1 / nxx);
}

void Test_fft_execute()
{

    ZF_LOGD("testing");

    double(*in)[nxx][nyy][nzz];
    double(*in2)[nxx][nyy][nzz];
    // double *in;

    fftw_complex(*out)[nxx][nyy][nzz/2+1];
    n_data_3D_double_init(nxx, nyy, nzz, &in);
    n_data_3D_double_init(nxx, nyy, nzz, &in2);
    out = calloc(nxx*nyy*(nzz/2+1),sizeof(fftw_complex));


    for (int i = 0; i < nxx; i++)
    {
        for (int j = 0; j < nyy; j++)
        {
            for (int k = 0; k < nzz; k++)
            {
                // ZF_LOGD("The in is: %i %i %i %i",i,j,k,sizeof(*in)/sizeof(*in[0][0][0]));
                if (i<nxx/2)
                {
                    (*in)[i][j][k] = i/10.0;
                }else{
                    (*in)[i][j][k] = (nxx-i-1)/10.0;
                }
                
                // (*in)[i][j][k] = 5;
                // in[k + j * 6 + i * 6 * 5] = i;
            }
        }
    }

    // for (int i = 0; i < nxx; i++)


    ZF_LOGD("finished setting the data");
    // n_fftw_r2c_3d_forward(5,6,7,*in, *out);
    n_fftw_r2c_3d_forward(&nfft,*in, *out);


    n_fftw_r2c_3d_backward(&nfft,*out, *in2);
    n_fftw_r2c_3d_derivative(&nfft,"r2c_3d/x",in,in2);
    for (int i = 0; i < nxx; i++)
    {
        for (int j = 0; j < 1; j++)
        {
            for (int k = 0; k < 1; k++)
            {
                ZF_LOGD("The in after is: %i %i %i %f %f", i, j, k, (*in)[i][j][k], (*in2)[i][j][k]);
            }
        }
    }

    TEST_ASSERT_EQUAL_INT(1, 1);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(Test_n_fft_setup);
    RUN_TEST(Test_fft_execute);
    return UNITY_END();
}