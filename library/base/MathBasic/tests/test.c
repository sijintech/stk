#include <unity.h>
#include <nTemplate/nTemplate.h>

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void test_ntemplate(){
    ZF_LOGI("Testing NTemplate");
    double (*data)[2][3][4];
    NTemplatePtr NTemplate_init(2,3,4,&data);
    NTemplate_fill(*data);
    NTemplate_print(*data);
    TEST_ASSERT_EQUAL_FLOAT(*data[0][0][1],1.0);
    TEST_ASSERT_EQUAL_FLOAT(*data[0][0][2],2.0);

}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_ntemplate)
    return UNITY_END();
}