#include <nstructuregenerator/structuregenerator.h>
#include <unity.h>
#include <unistd.h>

void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}

void test_n_material_generator(){
   char cwd[PATH_MAX];
   if (getcwd(cwd, sizeof(cwd)) != NULL) {
       printf("Current working dir: %s\n", cwd);
   } else {
       perror("getcwd() error");
   }

    char *index="1112";

    int phase_count = n_get_xml_element_count("input.xml","/input/material/phase" , "");

    double (*tensor)[phase_count][3][3];
    double (*stiffness)[phase_count][81];

    n_data_2D_double_init(phase_count,9,&tensor);
    
    n_data_2D_double_init(phase_count,81,&stiffness);
    n_material_generator(*tensor,"input.xml","/input/material","epsilon");
    // ZF_LOGI("The string after is %f %f",tensor[0][0],tensor[0][4],tensor[0][8]);
    n_material_tensor_print((*tensor)[0],2,"epsilon");
    TEST_ASSERT_EQUAL_FLOAT((*tensor)[0][0][0],123321);
    TEST_ASSERT_EQUAL_FLOAT((*tensor)[0][1][1],123321);
    TEST_ASSERT_EQUAL_FLOAT((*tensor)[0][2][2],123321);


    n_material_generator(*stiffness,"input.xml","/input/material","stiffness");
    n_material_tensor_print((*stiffness)[0],4,"stiffness");

}

int main(void){
    UNITY_BEGIN();
    RUN_TEST(test_n_material_generator);
    return UNITY_END();
}