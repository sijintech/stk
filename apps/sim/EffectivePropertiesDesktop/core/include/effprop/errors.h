#ifndef __SUANEFFPROPERRORS_H__
#define __SUANEFFPROPERRORS_H__

#include <effprop/effprop.h>

#ifdef __cplusplus
extern "C"{
#endif

typedef enum{
    SUANEFFPROP_ERR_GOOD           = 0,
    SUANEFFPROP_ERR_UNKNOWNKEYWORD = 1,
} SUANEFFError;

#ifdef __cplusplus
}
#endif


#endif /*__SUANEFFPROPERRORS_H__*/
