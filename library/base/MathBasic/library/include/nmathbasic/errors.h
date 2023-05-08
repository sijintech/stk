#ifndef __NMATHBASICERRORS_H__
#define __NMATHBASICERRORS_H__

#include <nmathbasic/exports.h>

#ifdef __cplusplus
extern "C"{
#endif

typedef enum{
    NMATHBASIC_ERR_GOOD           = 0,
    NMATHBASIC_ERR_UNKNOWNKEYWORD = 1,
} NIOError;

#ifdef __cplusplus
}
#endif


#endif /*__NMATHBASICERRORS_H__*/
