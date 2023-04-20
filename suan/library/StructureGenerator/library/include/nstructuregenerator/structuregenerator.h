#ifndef __STRUCTUREGENERATOR_H__
#define __STRUCTUREGENERATOR_H__

//#define _CRT_SECURE_NO_WARNINGS
#define _CRT_NONSTDC_NO_DEPRECATE

#include "niobasic/niobasic.h"
#include "nstructuregenerator/exports.h"
// #include "nstructuregenerator/material.h"
#include "nstructuregenerator/structures.h"
#include "ntextutils/ntextutils.h"
#include <libxml/parser.h>
#include <libxml/xpath.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef __cplusplus

extern "C" {
#endif

NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
n_generate_structure_from_file(int nx,
                               int ny,
                               int nz,
                               short dat[nx][ny][nz],
                               const char* fileName,
                               const char* path);
NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
n_structure_assign_data(int x,
                        int y,
                        int z,
                        int c,
                        double data[x][y][z][c],
                        short structure[x][y][z],
                        int compare,
                        double assignValue[c]);

NSTRUCTUREGENERATORPUBFUN void NSTRUCTUREGENERATORCALL
n_structure_assign_data_f(int* nx,
                          int* ny,
                          int* nz,
                          int* component,
                          double** dat,
                          short** structure,
                          int* compare,
                          double** assignValue);

#ifdef __cplusplus
}
#endif
#endif