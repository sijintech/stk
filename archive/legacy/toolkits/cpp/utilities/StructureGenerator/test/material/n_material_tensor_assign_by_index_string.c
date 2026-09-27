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

void test_n_material_tensor_assign_by_index_string(){
    char *index="1112";
    double tensor[81]={0};
    ZF_LOGI("The for tensor %p %p",tensor);

    n_material_tensor_assign_by_index_string(tensor,"1111",123.123);
    n_material_tensor_assign_by_index_string(tensor,"1113",456.123);
    ZF_LOGI("The string after is %f %f",tensor[0],tensor[2]);
    TEST_ASSERT_EQUAL_FLOAT(tensor[0],123.123);


}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_material_tensor_assign_by_index_string);
    return UNITY_END();
}