#include <nlicense/nlicense.h>
#include <effprop/effprop.h>
#include <zf_log.h>
#include <niobasic/niobasic.h>

int main(int argc, char *argv[])
{

    // int valid = n_License_verify("Suan-EffProp","0.0.1");

    // if (valid != NLICENSE_SUCCESS && valid!=NLICENSE_FAIL_GROUP && valid!=NLICENSE_FAIL_USERNAME && valid!=NLICENSE_FAIL_GROUP|NLICENSE_FAIL_USERNAME)
    // {
    //     ZF_LOGI("Not valid to use the Suan-EffProp simulation program.");
    //     return -1;
    // }

    ZF_LOGI("Start the effective property calculation");

    int valid = 0;
    // valid = n_License_verify("EffProp","1.0.0");
    char uid[128] = {'\0'};
    n_License_read_file(uid, "secret");
    ZF_LOGI("The uid %s", uid);
    valid = n_License_verify_mix("40756683cdc889144ae2d39de096eb9e", "1.0.0", uid);
    ZF_LOGI("valid %d", valid);
    if (valid != 0 && valid != 4)
    {
        ZF_LOGI("Not valid to use the EffProp simulation program.");
        return -1;
    }
    effective_property();

    return 0;
}