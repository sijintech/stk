#ifndef __NMATHBASICRANDOM_H__
#define __NMATHBASICRANDOM_H__

#include <nmathbasic/exports.h>
#include <nmathbasic/errors.h>


#ifdef __cplusplus
extern "C"{
#endif


  NMATHBASICPUBFUN  void NMATHBASICCALL n_random_init_by_time();
  NMATHBASICPUBFUN  void NMATHBASICCALL n_random_init_by_seed(int seed);
  NMATHBASICPUBFUN  double NMATHBASICCALL n_random_in_range(double lower, double upper);




#ifdef __cplusplus
}
#endif
#endif 
