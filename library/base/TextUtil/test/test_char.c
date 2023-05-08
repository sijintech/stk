//#define _CRT_SECURE_NO_WARNINGS
//#define _CRT_NONSTDC_NO_DEPRECATE
#include <unity.h>
#include <ntextutils/ntextutils.h>

void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}

void ten_char_exist(){
    int exist= n_char_exist("This is a string.",'i');
    TEST_ASSERT_EQUAL_INT(exist,1);
    exist= n_char_exist("This is a string.",'=');
    TEST_ASSERT_EQUAL_INT(exist,0);
}

void ten_string_exist(){
    int exist= n_string_exist("This is a string.","is");
    TEST_ASSERT_EQUAL_INT(exist,1);
    exist= n_string_exist("This is a string.","isa");
    TEST_ASSERT_EQUAL_INT(exist,0);
}

void ten_string_count(){
    int exist= n_string_count("This is a string.","i");
    TEST_ASSERT_EQUAL_INT(exist,3);
    exist= n_string_count("This is a strisng.","is");
    TEST_ASSERT_EQUAL_INT(exist,3);
}


void test_get_index(){
    int exist=n_substring_index("This is a string.","h");
    TEST_ASSERT_EQUAL_INT(exist,1);
    exist=n_substring_index("This is a string.","a");
    TEST_ASSERT_EQUAL_INT(exist,8);    
}

void test_equal(){
    int exist=n_string_equal("This is a string.","This is a string.");
    TEST_ASSERT_EQUAL_INT(exist,1);
    exist=n_string_equal("This is a strisng.","This is a string.");
    TEST_ASSERT_EQUAL_INT(exist,0);
}

void test_trim(){
    char output[MAX_STRING]=" asdfas \n\v";
    strcpy(output,n_string_trim_left(output,"\t\n\v\f\r a"));
    TEST_ASSERT_EQUAL_STRING(output,"sdfas \n\v");
    n_string_trim_right(output,"\t\n\v\f\r a");
    TEST_ASSERT_EQUAL_STRING(output,"sdfas");
    strcpy(output," asdfas \n\v");
    n_string_trim(output,"\t\n\v\f\r a");
    TEST_ASSERT_EQUAL_STRING(output,"sdfas");
}

void test_read_file(){
    char output[MAX_STRING];
    // int *filesize,*err;
    n_file_write_string( "testing.txt","testing file");
    n_file_read_string(output, "testing.txt");
    TEST_ASSERT_EQUAL_STRING(output,"testing file");

    char output1[MAX_STRING]={'\0'};
    n_file_write_fix_length_string("test_fix.txt", "Another testing gilfe",10);
    n_file_read_fix_length_string(output1, "test_fix.txt",10);
    TEST_ASSERT_EQUAL_CHAR(output1[0],'A');
    TEST_ASSERT_EQUAL_CHAR(output1[10],'\0');
}


void test_join(){
    char output[MAX_STRING];
    n_string_join(output,"hello","world"," ");
    TEST_ASSERT_EQUAL_STRING(output,"hello world");
}


void test_concat(){
    char output[MAX_STRING];
    n_string_concat(output, 5,"hello"," ","world"," ","welcome");
    TEST_ASSERT_EQUAL_STRING(output,"hello world welcome");
}


int main(void) {
    UNITY_BEGIN();
    RUN_TEST(ten_char_exist);
    RUN_TEST(ten_string_exist);
    RUN_TEST(ten_string_count);
    RUN_TEST(test_get_index);
    RUN_TEST(test_equal);
    RUN_TEST(test_trim);
    RUN_TEST(test_read_file);
    RUN_TEST(test_join);
    RUN_TEST(test_concat);
    return UNITY_END();
}