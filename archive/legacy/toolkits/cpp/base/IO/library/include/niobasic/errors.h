#ifndef __ERRORS_H__
#define __ERRORS_H__

#include <niobasic/exports.h>

#ifdef __cplusplus
extern "C"{
#endif

typedef enum{
    NIOBASIC_ERR_GOOD           = 0,
    NIOBASIC_ERR_UNKNOWNKEYWORD = 1,
    NIOBASIC_ERR_XMLFILEMISSING = 2,
} NIOBASICError;

#ifdef __cplusplus
}
#endif


#endif /*__ERRORS_H__*/
