#include "zf_log.h"

void zf_logv_f(const char *text){
    ZF_LOGV("%s",text);
}

void zf_logd_f(const char *text){
    ZF_LOGD("%s",text);
}

void zf_logi_f(const char *text){
    ZF_LOGI("%s",text);
}

void zf_logw_f(const char *text){
    ZF_LOGW("%s",text);
}

void zf_loge_f(const char *text){
    ZF_LOGE("%s",text);
}

void zf_logf_f(const char *text){
    ZF_LOGF("%s",text);
}
