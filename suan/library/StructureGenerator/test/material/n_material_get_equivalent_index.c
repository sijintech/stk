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

void test_n_material_get_equivalent_index(){
    int pg = 31;
    int rank = 4;
    char *index="1111";
    int sign=1;
    NStringArray tt;
    tt = n_material_get_equivalent_index( &sign, "Td", rank, index);
    ZF_LOGI("The sign is %i",sign);
    for (size_t i = 0; i < tt.length; i++)
    {
        ZF_LOGI("The tt string %i %s",i,tt.data[i]);    
    }
    
    TEST_ASSERT_EQUAL_STRING(tt.data[1],"2222");
}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_material_get_equivalent_index);
    return UNITY_END();
}