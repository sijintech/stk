#include <unity.h>
#include <ntextutils/ntextutils.h>

void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}

void test_n_NString_init(){
    NString output=n_NString_init("Hello world");
    TEST_ASSERT_EQUAL_STRING(output.data,"Hello world");
    TEST_ASSERT_EQUAL_INT(output.length,11);
}

void test_n_NStringPtr_init(){
    NStringPtr output=n_NStringPtr_init("Hello world");
    TEST_ASSERT_EQUAL_STRING(output->data,"Hello world");
    TEST_ASSERT_EQUAL_INT(output->length,11);
    n_NStringPtr_free(output);
}

void test_join(){
    NString a = n_NString_init("Hello");
    NString b = n_NString_init("World");
    NString output = n_NString_join(a,b," ");
    TEST_ASSERT_EQUAL_STRING(output.data,"Hello World");
    TEST_ASSERT_EQUAL_INT(output.length,11);
}

void test_split(){
    NString first=n_string_split_first_by_index("Testing line of string"," ");
    NString rest=n_string_split_rest_by_index("Testing line of string"," ");
    TEST_ASSERT_EQUAL_STRING(first.data,"Testing");
    TEST_ASSERT_EQUAL_STRING(rest.data,"line of string");
    first=n_string_split_first_by_index("Testing"," ");
    rest=n_string_split_rest_by_index("Testing"," ");
    TEST_ASSERT_EQUAL_STRING(first.data,"Testing");
    TEST_ASSERT_EQUAL_STRING(rest.data,"");
}

void test_time(){
    NString time=n_current_time_as_string();
    NString future=n_future_time_as_string(0);
    TEST_ASSERT_EQUAL_STRING(time.data,future.data);

}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_n_NString_init);
    RUN_TEST(test_n_NStringPtr_init);
    RUN_TEST(test_join);
    RUN_TEST(test_split);
    RUN_TEST(test_time);

    return UNITY_END();
}