#include <unity.h>
#include <zf_log.h>
#include "nmath/nmath.h"

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void Test_Matrix(){
    double(*data)[5][10];
    init_2D_data_double(5, 10, &data);
    fill_2D_data_double(5, 10, *data);
    print_2D_data_double(5, 10, *data);
    TEST_ASSERT_EQUAL_FLOAT(*data[0][1],1.0);
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(Test_Matrix);
    return UNITY_END();
}