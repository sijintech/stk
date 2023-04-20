#include <unity.h>
#include <ntextutils/ntextutils.h>

void setUp(void) {
    // set stuff up here
}

void tearDown(void) {
    // clean stuff up here
}


void test_read_file(){
    char output[MAX_STRING]={'\0'};
    n_file_write_fix_length_string("test_hex.txt", "Another testing gilfe",2048);
    n_file_hex_read_string(output, "test_hex.txt",2048);
    printf("The hex %s",output);
}



int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_read_file);
    return UNITY_END();
}