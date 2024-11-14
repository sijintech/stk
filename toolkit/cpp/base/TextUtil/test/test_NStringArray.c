// #include <criterion/criterion.h>
#include <unity.h>
#include <ntextutils/ntextutils.h>

extern void ten_char_exist(void);

void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}


void ten_string_split_two(){
    NStringArray out=n_string_split("-aaa=bbbb=ccc-ddd","=-");
    TEST_ASSERT_EQUAL_STRING (out.data[0],"");
    TEST_ASSERT_EQUAL_STRING (out.data[1],"aaa");
    TEST_ASSERT_EQUAL_STRING (out.data[2],"bbbb");
    TEST_ASSERT_EQUAL_STRING (out.data[3],"ccc");
    TEST_ASSERT_EQUAL_STRING (out.data[0],"");
    TEST_ASSERT_EQUAL_STRING (out.data[1],"aaa");
    TEST_ASSERT_EQUAL_STRING (out.data[2],"bbbb");
    TEST_ASSERT_EQUAL_STRING (out.data[3],"ccc");
    TEST_ASSERT_EQUAL_STRING (out.data[4],"ddd");
    TEST_ASSERT(out.length==5);
}

void ten_string_split_three(){
    NStringArray out=n_string_split("123+test=5353-123","=+-");
    TEST_ASSERT_EQUAL_STRING(out.data[1],"test");
    TEST_ASSERT_EQUAL_STRING(out.data[2],"5353");
    TEST_ASSERT_EQUAL_STRING(out.data[3],"123");
    TEST_ASSERT_EQUAL_STRING(out.data[0],"123");
    TEST_ASSERT(out.length==4);
}

void test_join(){
    NStringArray out=n_NStringArray_init(4);
    strcpy(out.data[0],"test");
    strcpy(out.data[1],"1222");
    strcpy(out.data[2],"2333");
    strcpy(out.data[3],"333");
    NString test=n_NStringArray_join(out,"+");
    TEST_ASSERT_EQUAL_STRING(test.data,"test+1222+2333+333");
}

void test_contain_index(){
    NStringArray out=n_NStringArray_init(4);
    strcpy(out.data[0],"test");
    strcpy(out.data[1],"1222");
    strcpy(out.data[2],"2333");
    strcpy(out.data[3],"333");
    int exist=n_NStringArray_contain_string(out,"test");
    TEST_ASSERT_EQUAL_INT(exist,1);    
    exist=n_NStringArray_string_index(out,"333");
    TEST_ASSERT_EQUAL_INT(exist,3);    
}


// not needed when using generate_test_runner.rb
int main(void) {
    UNITY_BEGIN();
    RUN_TEST(ten_string_split_two);
    RUN_TEST(ten_string_split_three);
    RUN_TEST(test_join);
    RUN_TEST(test_contain_index);
    return UNITY_END();
}