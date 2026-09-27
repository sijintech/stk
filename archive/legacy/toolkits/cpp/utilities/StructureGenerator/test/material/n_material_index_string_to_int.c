#include <nstructuregenerator/structuregenerator.h>
#include <unity.h>

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void test_n_material_index_string_to_int(){
    char *index="1112";
    int tt=0;
    ZF_LOGI("The string before is %i",tt);
    tt = n_material_index_string_to_int(index);
    ZF_LOGI("The string after is %i",tt);
    TEST_ASSERT_EQUAL_INT(tt,1);

    tt = n_material_index_string_to_int("1121");
    ZF_LOGI("The string after is %i",tt);
    TEST_ASSERT_EQUAL_INT(tt,3);
}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_material_index_string_to_int);
    return UNITY_END();
}