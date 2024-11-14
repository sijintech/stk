// #define ZF_LOG_LEVEL ZF_LOG_VERBOSE
#include <unity.h>
#include <zf_log.h>
#include "basic/controlFile.h"
#include "ntextutils/ntextutils.h"
#include <stdlib.h>
// ZF_LOG_VERBOSE 1
// DEBUG 2
// INFO 3
// WARN 4
// ERROR 5
// FATAL 6
// NONE 7
// Testing cases for string, the stringutils.h and stringutils.c

void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}


// Testing for xml reader, controlfile.h and controlfile.c
void Test_XML_n_get_text_by_xpath(){
    ControlFilePtr control=n_ControlFile_init("test.xml",NULL);
    char out[MAX_STRING];
    n_ControlFile_get_text_by_xpath(out,control->doc,"//elastic/bc","testing text xpath");
    n_ControlFile_free(control);
    TEST_ASSERT_EQUAL_STRING(out,"2");
}

void Test_XML_n_get_int_by_xpath(){
    ControlFilePtr control=n_ControlFile_init("test.xml",NULL);
    int out=n_ControlFile_get_int_by_xpath(control->doc,"//elastic/bc","testing int xpath");
    n_ControlFile_free(control);
    TEST_ASSERT(out==2);
}

void Test_XML_n_get_double_by_xpath(){
    ControlFilePtr control=n_ControlFile_init("test.xml",NULL);
    double out=n_ControlFile_get_double_by_xpath(control->doc,"//elastic/bc","testing double xpath");
    n_ControlFile_free(control);
    TEST_ASSERT(out<2.001&&out>1.999);
}

void Test_XML_n_get_bool_by_xpath(){
    ControlFilePtr control=n_ControlFile_init("test.xml",NULL);
    int out=n_ControlFile_get_bool_by_xpath(control->doc,"//elastic/switch","testing bool xpath");
    n_ControlFile_free(control);
    TEST_ASSERT(out==1);
}

void Test_XML_get_int(){
    int a=n_get_xml_element_as_int("test.xml","//elastic/bc","testing int");
    TEST_ASSERT(a==2);
}

void Test_XML_get_double(){
    double a=n_get_xml_element_as_double("test.xml","//elastic/bc","testing double");
    TEST_ASSERT(a<2.001&&a>1.999);
}

void Test_XML_get_array(){
    NStringArray test=n_get_xml_element_as_NStringArray("test.xml","//host","testing array");
    TEST_ASSERT_EQUAL_INT(test.length,2);
    TEST_ASSERT_EQUAL_STRING(test.data[0],"1");
    TEST_ASSERT_EQUAL_STRING(test.data[1],"2");
}

void Test_XML_set_text(){
    remove("new_test.xml");
    n_set_xml_element_by_string("hello","new_test.xml","/client/type",1,"");
    n_set_xml_element_by_string("falcon","new_test.xml","/client/hostname",1,"");
    n_set_xml_element_by_string("test2hostname","new_test.xml","/client/hostname",1,"");
    NStringArray temp;
    temp.length=2;
    strcpy(temp.data[0],"test");
    strcpy(temp.data[1],"array");
    n_set_xml_element_by_NStringArray(temp,"new_test.xml","/client/host","");

    char out[MAX_STRING];
    n_get_xml_element_as_string(out,"new_test.xml","/client/type","");
    temp=n_get_xml_element_as_NStringArray("new_test.xml","/client/host","");

    TEST_ASSERT_EQUAL_STRING(out,"hello");
    TEST_ASSERT_EQUAL_STRING(temp.data[0],"test");
}

void Test_XML_set_text_memory(){
    char memory[MAX_STRING]={'\0'};
    n_set_xml_element_by_string_to_memory("hello",memory,"/client/type",1,"");
    n_set_xml_element_by_string_to_memory("falcon",memory,"/client/hostname",1,"");
    NStringArray temp;
    temp.length=2;
    strcpy(temp.data[0],"test");
    strcpy(temp.data[1],"array");
    ZF_LOGD("set text memeory,%s",memory);
    n_set_xml_element_by_NStringArray_to_memory(temp,memory,"/client/host","");
    char out[MAX_STRING];
    n_get_xml_element_as_string_from_memory(out,memory,"/client/type","");
    temp = n_get_xml_element_as_NStringArray_from_memory(memory,"/client/host","");
    ZF_LOGD("set text memeory,%s",out);
    TEST_ASSERT_EQUAL_STRING(out,"hello");
    TEST_ASSERT_EQUAL_STRING(temp.data[0],"test");
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(Test_XML_n_get_text_by_xpath);
    RUN_TEST(Test_XML_n_get_int_by_xpath);
    RUN_TEST(Test_XML_n_get_double_by_xpath);
    RUN_TEST(Test_XML_n_get_bool_by_xpath);
    RUN_TEST(Test_XML_get_int);
    RUN_TEST(Test_XML_get_double);
    RUN_TEST(Test_XML_get_array);
    RUN_TEST(Test_XML_set_text);
    RUN_TEST(Test_XML_set_text_memory);
    return UNITY_END();
}