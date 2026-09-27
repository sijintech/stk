#include <unity.h>
#include <zf_log.h>
#include "niobasic/vtiFile.h"
#include "nmath/nmath.h"
#include "niobasic/controlFile.h"
#include "ntextutils/ntextutils.h"
void setUp(void)
{
    // set stuff up here
}

void tearDown(void)
{
    // clean stuff up here
}


void Test_VTI_ImageData_write()
{
    double(*data)[5][1][2][2];
    init_4D_data_double(5, 1, 2, 2, &data);

    remove("new_test.xml");
    n_set_xml_element_by_string("hello","new_test.xml","/client/type",1,"");
    remove("new_test.xml");
    remove("test.vti");
    fill_4D_data_double(5, 1, 2,2, *data);
    print_4D_data_double(5, 1, 2,2, *data);

    n_vtiFile_4D_double_write(5, 1, 2, 2, *data, "test.vti");
}

void Test_VTI_ImageData_read(){
    int(*data)[5][1][2];
    init_3D_data_int(5, 1, 2, &data);
    n_vtiFile_3D_int_read(5,1,2,*data,"initial_int.vti");
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(Test_VTI_ImageData_write);
    RUN_TEST(Test_VTI_ImageData_read);
    return UNITY_END();
}