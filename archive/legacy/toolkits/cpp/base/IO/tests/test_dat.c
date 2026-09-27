#include <unity.h>
#include <zf_log.h>
#include "niobasic/datFile.h"


void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}

void Test_dat_init(){
    DatPtr_4D_double test = Dat_4D_double_init(1,2,3,4);
    Dat_4D_double_free(test);
}

void Test_dat_set_get(){
    DatPtr_4D_double test = Dat_4D_double_init(1,2,3,4);
    // ZF_LOGD("t pass");
    Dat_4D_double_set(test,0,0,0,1,1.0);
    double t=Dat_4D_double_get(test,0,0,0,1);
    // ZF_LOGD("t: %lf",t);
    TEST_ASSERT_EQUAL_FLOAT(t,1.0);
    // ZF_LOGD("t pass");
    Dat_4D_double_free(test);
}

void Test_dat_write(){
    DatPtr_4D_double test = Dat_4D_double_init(1,2,3,4);
    Dat_4D_double_set(test,0,0,0,1,1.0);
    Dat_4D_double_set(test,0,0,2,2,3.0);
    DatFile_4D_double_write(test,"test.dat");

    double t=Dat_4D_double_get(test,0,0,2,2);
    TEST_ASSERT_EQUAL_FLOAT(t,3.0);
    Dat_4D_double_free(test);    
}

void Test_dat_read(){
    DatPtr_4D_double test = Dat_4D_double_init(1,2,3,4);
    n_datFile_4D_double_read(test,"test.dat");
    double t=Dat_4D_double_get(test,0,0,0,1);
    // ZF_LOGD("double %lf",t);
    TEST_ASSERT_EQUAL_FLOAT(t,1.0);
    t=Dat_4D_double_get(test,0,0,2,2);
    TEST_ASSERT_EQUAL_FLOAT(t,3.0);
    Dat_4D_double_free(test);        
}

int main(void ){
    UNITY_BEGIN();
    RUN_TEST(Test_dat_init);
    RUN_TEST(Test_dat_set_get);
    RUN_TEST(Test_dat_write);
    RUN_TEST(Test_dat_read);
    return UNITY_END();
}