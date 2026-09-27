/* Point_Group Chart, from International Table for Crystallography Vol. D
Physical properties of crystals Index: Notation
 1: 1, C1
 2: \bar{1}, S2
 3: 2, C2
 4: m, C1h, C1v, Cs
 5: 2/m, C2h
 6: 222, D2
 7: mm2, C2v
 8: mmm, D2h
 9: 4, C4
10: \bar{4}, S4
11: 4/m, C4h
12: 422, D4
13: 4mm, C4v
14: \bar{4}2m, D2d
15: 4/m mm, D4h
16: 3, C3
17: \bar{3}, S6, C3i
18: 32, D3
19: 3m, C3v
20: \bar{3} m, D3d
21: 6, C6
22: \bar{6}, C3h
23: 6/m, C6h
24: 622, D6
25: 6mm, C6v
26: \bar{6}m2, D3h
27: 6/m mm, D6h
28: 23, T
29: m\bar{3}, Th
30: 432, O
31: \bar{4}3m, Td
32: m\bar{3}m, Oh
33: curie1
34: curie2
*/

#include "nstructuregenerator/material.h"

#define empty_constrain                                                        \
    {                                                                          \
        0,                                                                     \
        {                                                                      \
            1, { "1111" }                                                      \
        }                                                                      \
    }

// isotropic elastic constant 2 independent, 3 unique
#define isotropicr4_1                                                          \
    {                                                                          \
        3, { "1111", "2222", "3333" }                                          \
    }
#define isotropicr4_2                                                          \
    {                                                                          \
        6, { "1122", "1133", "2233", "2211", "3311", "3322" }                  \
    }
#define isotropicr4_3                                                          \
    {                                                                          \
        12,                                                                    \
        {                                                                      \
            "2323", "3131", "1212", "3232", "1313", "2121", "2332", "3113",    \
                "1221", "3223", "1331", "2112"                                 \
        }                                                                      \
    }
#define isotropicr4_c1                                                         \
    {                                                                          \
        2, { "1111-1122", "1212" }                                             \
    }

// 30: 432, O
PointGroup IsotropicRank4 = {
    21, 3, 2, {isotropicr4_1, isotropicr4_2, isotropicr4_3}};
PGConstrain IsotropicRank4_constrain = {1, {isotropicr4_c1}};

// 30,31,32 from 1.1.4.9.7.2, 4 independent
#define pg30r4_1                                                               \
    {                                                                          \
        3, { "1111", "2222", "3333" }                                          \
    }
#define pg30r4_2                                                               \
    {                                                                          \
        6, { "1122", "1133", "2233", "2211", "3311", "3322" }                  \
    }
#define pg30r4_3                                                               \
    {                                                                          \
        6, { "2323", "3131", "1212", "3232", "1313", "2121" }                  \
    }
#define pg30r4_4                                                               \
    {                                                                          \
        6, { "2332", "3113", "1221", "3223", "1331", "2112" }                  \
    }
// 30: 432, O
#define pg30r4                                                                 \
    {                                                                          \
        21, 4, 4, { pg30r4_1, pg30r4_2, pg30r4_3, pg30r4_4 }                   \
    }
#define pg30r4_constrain empty_constrain
// 31: \bar{4}3m, Td
#define pg31r4                                                                 \
    {                                                                          \
        21, 4, 4, { pg30r4_1, pg30r4_2, pg30r4_3, pg30r4_4 }                   \
    }
#define pg31r4_constrain empty_constrain
// 32: m\bar{3}m, Oh
#define pg32r4                                                                 \
    {                                                                          \
        21, 4, 4, { pg30r4_1, pg30r4_2, pg30r4_3, pg30r4_4 }                   \
    }
#define pg32r4_constrain empty_constrain

// 28, 29 from 1.1.4.9.7.1, 7 independent
#define pg28r4_1                                                               \
    {                                                                          \
        3, { "1111", "2222", "3333" }                                          \
    }
#define pg28r4_2                                                               \
    {                                                                          \
        4, { "1122", "2233", "2211", "3322" }                                  \
    }
#define pg28r4_3                                                               \
    {                                                                          \
        2, { "1133", "3311" }                                                  \
    }
#define pg28r4_4                                                               \
    {                                                                          \
        3, { "2323", "3131", "1212" }                                          \
    }
#define pg28r4_5                                                               \
    {                                                                          \
        3, { "3232", "1313", "2121" }                                          \
    }
#define pg28r4_6                                                               \
    {                                                                          \
        3, { "2332", "3113", "1221" }                                          \
    }
#define pg28r4_7                                                               \
    {                                                                          \
        3, { "3223", "1331", "2112" }                                          \
    }
// 28: 23,
#define pg28r4                                                                 \
    {                                                                          \
        21, 7, 7,                                                              \
        {                                                                      \
            pg28r4_1, pg28r4_2, pg28r4_3, pg28r4_4, pg28r4_5, pg28r4_6,        \
                pg28r4_7                                                       \
        }                                                                      \
    }
#define pg28r4_constrain empty_constrain
// 29: m\bar{3}, Th
#define pg29r4                                                                 \
    {                                                                          \
        21, 7, 7,                                                              \
        {                                                                      \
            pg28r4_1, pg28r4_2, pg28r4_3, pg28r4_4, pg28r4_5, pg28r4_6,        \
                pg28r4_7                                                       \
        }                                                                      \
    }
#define pg29r4_constrain empty_constrain

// 24, 25, 26, 27 from 1.1.4.9.6.2, the book said 11 independent, but I think
// there is only 10
#define pg24r4_1                                                               \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg24r4_2                                                               \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg24r4_3                                                               \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg24r4_4                                                               \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg24r4_5                                                               \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg24r4_6                                                               \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg24r4_7                                                               \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg24r4_8                                                               \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg24r4_9                                                               \
    {                                                                          \
        2, { "2332", "1331" }                                                  \
    }
#define pg24r4_10                                                              \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg24r4_11                                                              \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
#define pg24r4_c1                                                              \
    {                                                                          \
        2, { "1111-1122", "1212+1221" }                                        \
    }
// 27: 6/m mm,
#define pg27r4                                                                 \
    {                                                                          \
        21, 11, 10,                                                            \
        {                                                                      \
            pg24r4_1, pg24r4_2, pg24r4_3, pg24r4_4, pg24r4_5, pg24r4_6,        \
                pg24r4_7, pg24r4_8, pg24r4_9, pg24r4_10, pg24r4_11             \
        }                                                                      \
    }
#define pg27r4_constrain                                                       \
    {                                                                          \
        1, { pg24r4_c1 }                                                       \
    }
// 26: \bar{6}m2,
#define pg26r4                                                                 \
    {                                                                          \
        21, 11, 10,                                                            \
        {                                                                      \
            pg24r4_1, pg24r4_2, pg24r4_3, pg24r4_4, pg24r4_5, pg24r4_6,        \
                pg24r4_7, pg24r4_8, pg24r4_9, pg24r4_10, pg24r4_11             \
        }                                                                      \
    }
#define pg26r4_constrain                                                       \
    {                                                                          \
        1, { pg24r4_c1 }                                                       \
    }
// 25: 6mm,
#define pg25r4                                                                 \
    {                                                                          \
        21, 11, 10,                                                            \
        {                                                                      \
            pg24r4_1, pg24r4_2, pg24r4_3, pg24r4_4, pg24r4_5, pg24r4_6,        \
                pg24r4_7, pg24r4_8, pg24r4_9, pg24r4_10, pg24r4_11             \
        }                                                                      \
    }
#define pg25r4_constrain                                                       \
    {                                                                          \
        1, { pg24r4_c1 }                                                       \
    }
// 24: 622,
#define pg24r4                                                                 \
    {                                                                          \
        21, 11, 10,                                                            \
        {                                                                      \
            pg24r4_1, pg24r4_2, pg24r4_3, pg24r4_4, pg24r4_5, pg24r4_6,        \
                pg24r4_7, pg24r4_8, pg24r4_9, pg24r4_10, pg24r4_11             \
        }                                                                      \
    }
#define pg24r4_constrain                                                       \
    {                                                                          \
        1, { pg24r4_c1 }                                                       \
    }

// 21, 22, 23, from 1.1.4.9.6.1, 19 independent
#define pg21r4_1                                                               \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg21r4_2                                                               \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg21r4_3                                                               \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg21r4_4                                                               \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg21r4_5                                                               \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg21r4_6                                                               \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg21r4_7                                                               \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg21r4_8                                                               \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg21r4_9                                                               \
    {                                                                          \
        2, { "2332", "1331" }                                                  \
    }
#define pg21r4_10                                                              \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg21r4_11                                                              \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
#define pg21r4_12                                                              \
    {                                                                          \
        2, { "1112", "-2221" }                                                 \
    }
#define pg21r4_13                                                              \
    {                                                                          \
        2, { "1121", "-2212" }                                                 \
    }
#define pg21r4_14                                                              \
    {                                                                          \
        2, { "3312", "-3321" }                                                 \
    }
#define pg21r4_15                                                              \
    {                                                                          \
        2, { "1211", "-2122" }                                                 \
    }
#define pg21r4_16                                                              \
    {                                                                          \
        2, { "1222", "-2111" }                                                 \
    }
#define pg21r4_17                                                              \
    {                                                                          \
        2, { "1233", "-2133" }                                                 \
    }
#define pg21r4_18                                                              \
    {                                                                          \
        2, { "2331", "-1332" }                                                 \
    }
#define pg21r4_19                                                              \
    {                                                                          \
        2, { "3123", "-3213" }                                                 \
    }
#define pg21r4_20                                                              \
    {                                                                          \
        2, { "2313", "-1323" }                                                 \
    }
#define pg21r4_21                                                              \
    {                                                                          \
        2, { "3132", "-3231" }                                                 \
    }
#define pg21r4_c1                                                              \
    {                                                                          \
        2, { "1221+1212", "1111-1122" }                                        \
    }
#define pg21r4_c2                                                              \
    {                                                                          \
        2, { "1112+1121", "-1211-2111" }                                       \
    }
// 23: 6/m,
#define pg23r4                                                                 \
    {                                                                          \
        41, 21, 19,                                                            \
        {                                                                      \
            pg21r4_1, pg21r4_2, pg21r4_3, pg21r4_4, pg21r4_5, pg21r4_6,        \
                pg21r4_7, pg21r4_8, pg21r4_9, pg21r4_10, pg21r4_11, pg21r4_12, \
                pg21r4_13, pg21r4_14, pg21r4_15, pg21r4_16, pg21r4_17,         \
                pg21r4_18, pg21r4_19, pg21r4_20, pg21r4_21                     \
        }                                                                      \
    }
#define pg23r4_constrain                                                       \
    {                                                                          \
        2, { pg21r4_c1, pg21r4_c2 }                                            \
    }
// 22: \bar{6},
#define pg22r4                                                                 \
    {                                                                          \
        41, 21, 19,                                                            \
        {                                                                      \
            pg21r4_1, pg21r4_2, pg21r4_3, pg21r4_4, pg21r4_5, pg21r4_6,        \
                pg21r4_7, pg21r4_8, pg21r4_9, pg21r4_10, pg21r4_11, pg21r4_12, \
                pg21r4_13, pg21r4_14, pg21r4_15, pg21r4_16, pg21r4_17,         \
                pg21r4_18, pg21r4_19, pg21r4_20, pg21r4_21                     \
        }                                                                      \
    }
#define pg22r4_constrain                                                       \
    {                                                                          \
        2, { pg21r4_c1, pg21r4_c2 }                                            \
    }
// 21: 6,
#define pg21r4                                                                 \
    {                                                                          \
        41, 21, 19,                                                            \
        {                                                                      \
            pg21r4_1, pg21r4_2, pg21r4_3, pg21r4_4, pg21r4_5, pg21r4_6,        \
                pg21r4_7, pg21r4_8, pg21r4_9, pg21r4_10, pg21r4_11, pg21r4_12, \
                pg21r4_13, pg21r4_14, pg21r4_15, pg21r4_16, pg21r4_17,         \
                pg21r4_18, pg21r4_19, pg21r4_20, pg21r4_21                     \
        }                                                                      \
    }
#define pg21r4_constrain                                                       \
    {                                                                          \
        2, { pg21r4_c1, pg21r4_c2 }                                            \
    }

// 18, 19, 20, 1.1.4.9.2, 14 independent components
#define pg18r4_1                                                               \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg18r4_2                                                               \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg18r4_3                                                               \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg18r4_4                                                               \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg18r4_5                                                               \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg18r4_6                                                               \
    {                                                                          \
        4, { "1123", "-2223", "1213", "2113" }                                 \
    }
#define pg18r4_7                                                               \
    {                                                                          \
        4, { "1132", "-2232", "1231", "2131" }                                 \
    }
#define pg18r4_8                                                               \
    {                                                                          \
        4, { "2311", "-2322", "1312", "1321" }                                 \
    }
#define pg18r4_9                                                               \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg18r4_10                                                              \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg18r4_11                                                              \
    {                                                                          \
        4, { "3112", "3121", "3211", "-3222" }                                 \
    }
#define pg18r4_12                                                              \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg18r4_13                                                              \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg18r4_14                                                              \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
#define pg18r4_15                                                              \
    {                                                                          \
        2, { "1331", "2332" }                                                  \
    }
#define pg18r4_c1                                                              \
    {                                                                          \
        2, { "1111-1122", "1212+2121" }                                        \
    }
// 20: \bar{3} m,
#define pg20r4                                                                 \
    {                                                                          \
        37, 15, 14,                                                            \
        {                                                                      \
            pg18r4_1, pg18r4_2, pg18r4_3, pg18r4_4, pg18r4_5, pg18r4_6,        \
                pg18r4_7, pg18r4_8, pg18r4_9, pg18r4_10, pg18r4_11, pg18r4_12, \
                pg18r4_13, pg18r4_14, pg18r4_15                                \
        }                                                                      \
    }
#define pg20r4_constrain                                                       \
    {                                                                          \
        1, { pg18r4_c1 }                                                       \
    }
// 19: 3m,
#define pg19r4                                                                 \
    {                                                                          \
        37, 15, 14,                                                            \
        {                                                                      \
            pg18r4_1, pg18r4_2, pg18r4_3, pg18r4_4, pg18r4_5, pg18r4_6,        \
                pg18r4_7, pg18r4_8, pg18r4_9, pg18r4_10, pg18r4_11, pg18r4_12, \
                pg18r4_13, pg18r4_14, pg18r4_15                                \
        }                                                                      \
    }
#define pg19r4_constrain                                                       \
    {                                                                          \
        1, { pg18r4_c1 }                                                       \
    }
// 18: 32,
#define pg18r4                                                                 \
    {                                                                          \
        37, 15, 14,                                                            \
        {                                                                      \
            pg18r4_1, pg18r4_2, pg18r4_3, pg18r4_4, pg18r4_5, pg18r4_6,        \
                pg18r4_7, pg18r4_8, pg18r4_9, pg18r4_10, pg18r4_11, pg18r4_12, \
                pg18r4_13, pg18r4_14, pg18r4_15                                \
        }                                                                      \
    }
#define pg18r4_constrain                                                       \
    {                                                                          \
        1, { pg18r4_c1 }                                                       \
    }

// 16, 17, 1.1.4.9.4.1, 27 independent components
#define pg16r4_1                                                               \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg16r4_2                                                               \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg16r4_3                                                               \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg16r4_4                                                               \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg16r4_5                                                               \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg16r4_6                                                               \
    {                                                                          \
        4, { "1123", "-2223", "1213", "2113" }                                 \
    }
#define pg16r4_7                                                               \
    {                                                                          \
        4, { "1132", "-2232", "1231", "2131" }                                 \
    }
#define pg16r4_8                                                               \
    {                                                                          \
        4, { "2311", "-2322", "1312", "1321" }                                 \
    }
#define pg16r4_9                                                               \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg16r4_10                                                              \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg16r4_11                                                              \
    {                                                                          \
        4, { "3112", "3121", "3211", "-3222" }                                 \
    }
#define pg16r4_12                                                              \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg16r4_13                                                              \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg16r4_14                                                              \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
#define pg16r4_15                                                              \
    {                                                                          \
        2, { "1331", "2332" }                                                  \
    }
#define pg16r4_16                                                              \
    {                                                                          \
        2, { "1112", "-2221" }                                                 \
    }
#define pg16r4_17                                                              \
    {                                                                          \
        2, { "2212", "-1121" }                                                 \
    }
#define pg16r4_18                                                              \
    {                                                                          \
        2, { "3312", "-3321" }                                                 \
    }
#define pg16r4_19                                                              \
    {                                                                          \
        4, { "2231", "-1131", "1232", "2132" }                                 \
    }
#define pg16r4_20                                                              \
    {                                                                          \
        4, { "2213", "-1113", "2123", "1223" }                                 \
    }
#define pg16r4_21                                                              \
    {                                                                          \
        4, { "3122", "-3111", "3212", "3221" }                                 \
    }
#define pg16r4_22                                                              \
    {                                                                          \
        2, { "1211", "-2122" }                                                 \
    }
#define pg16r4_23                                                              \
    {                                                                          \
        2, { "2111", "-1222" }                                                 \
    }
#define pg16r4_24                                                              \
    {                                                                          \
        2, { "1233", "-2133" }                                                 \
    }
#define pg16r4_25                                                              \
    {                                                                          \
        2, { "2331", "-1332" }                                                 \
    }
#define pg16r4_26                                                              \
    {                                                                          \
        2, { "3123", "-3213" }                                                 \
    }
#define pg16r4_27                                                              \
    {                                                                          \
        2, { "3132", "-3231" }                                                 \
    }
#define pg16r4_28                                                              \
    {                                                                          \
        4, { "1322", "-1311", "2312", "2321" }                                 \
    }
#define pg16r4_29                                                              \
    {                                                                          \
        2, { "2313", "-1323" }                                                 \
    }
#define pg16r4_c1                                                              \
    {                                                                          \
        2, { "1111-1122", "1212+2121" }                                        \
    }
#define pg16r4_c2                                                              \
    {                                                                          \
        2, { "1112+1121", "-1211-2111" }                                       \
    }
// 16: 3
#define pg16r4                                                                 \
    {                                                                          \
        73, 29, 27,                                                            \
        {                                                                      \
            pg16r4_1, pg16r4_2, pg16r4_3, pg16r4_4, pg16r4_5, pg16r4_6,        \
                pg16r4_7, pg16r4_8, pg16r4_9, pg16r4_10, pg16r4_11, pg16r4_12, \
                pg16r4_13, pg16r4_14, pg16r4_15, pg16r4_16, pg16r4_17,         \
                pg16r4_18, pg16r4_19, pg16r4_20, pg16r4_21, pg16r4_22,         \
                pg16r4_23, pg16r4_24, pg16r4_25, pg16r4_26, pg16r4_27,         \
                pg16r4_28, pg16r4_29                                           \
        }                                                                      \
    }
#define pg16r4_constrain                                                       \
    {                                                                          \
        2, { pg16r4_c1, pg16r4_c2 }                                            \
    }
// 17: \bar{3}
#define pg17r4                                                                 \
    {                                                                          \
        73, 29, 27,                                                            \
        {                                                                      \
            pg16r4_1, pg16r4_2, pg16r4_3, pg16r4_4, pg16r4_5, pg16r4_6,        \
                pg16r4_7, pg16r4_8, pg16r4_9, pg16r4_10, pg16r4_11, pg16r4_12, \
                pg16r4_13, pg16r4_14, pg16r4_15, pg16r4_16, pg16r4_17,         \
                pg16r4_18, pg16r4_19, pg16r4_20, pg16r4_21, pg16r4_22,         \
                pg16r4_23, pg16r4_24, pg16r4_25, pg16r4_26, pg16r4_27,         \
                pg16r4_28, pg16r4_29                                           \
        }                                                                      \
    }
#define pg17r4_constrain                                                       \
    {                                                                          \
        2, { pg16r4_c1, pg16r4_c2 }                                            \
    }

// 12, 13, 14, 15, 1.1.4.9.5.2, 11 independent components
#define pg12r4_1                                                               \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg12r4_2                                                               \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg12r4_3                                                               \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg12r4_4                                                               \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg12r4_5                                                               \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg12r4_6                                                               \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg12r4_7                                                               \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg12r4_8                                                               \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg12r4_9                                                               \
    {                                                                          \
        2, { "1331", "2332" }                                                  \
    }
#define pg12r4_10                                                              \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg12r4_11                                                              \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
// 15: 4/m mm
#define pg15r4                                                                 \
    {                                                                          \
        21, 11, 11,                                                            \
        {                                                                      \
            pg12r4_1, pg12r4_2, pg12r4_3, pg12r4_4, pg12r4_5, pg12r4_6,        \
                pg12r4_7, pg12r4_8, pg12r4_9, pg12r4_10, pg12r4_11             \
        }                                                                      \
    }
#define pg15r4_constrain empty_constrain
// 14: \bar{4}2m
#define pg14r4                                                                 \
    {                                                                          \
        21, 11, 11,                                                            \
        {                                                                      \
            pg12r4_1, pg12r4_2, pg12r4_3, pg12r4_4, pg12r4_5, pg12r4_6,        \
                pg12r4_7, pg12r4_8, pg12r4_9, pg12r4_10, pg12r4_11             \
        }                                                                      \
    }
#define pg14r4_constrain empty_constrain
// 13: 4mm
#define pg13r4                                                                 \
    {                                                                          \
        21, 11, 11,                                                            \
        {                                                                      \
            pg12r4_1, pg12r4_2, pg12r4_3, pg12r4_4, pg12r4_5, pg12r4_6,        \
                pg12r4_7, pg12r4_8, pg12r4_9, pg12r4_10, pg12r4_11             \
        }                                                                      \
    }
#define pg13r4_constrain empty_constrain
// 12: 422
#define pg12r4                                                                 \
    {                                                                          \
        21, 11, 11,                                                            \
        {                                                                      \
            pg12r4_1, pg12r4_2, pg12r4_3, pg12r4_4, pg12r4_5, pg12r4_6,        \
                pg12r4_7, pg12r4_8, pg12r4_9, pg12r4_10, pg12r4_11             \
        }                                                                      \
    }
#define pg12r4_constrain empty_constrain

// 9, 10, 11, 1.1.4.9.5.1 21 independent
#define pg9r4_1                                                                \
    {                                                                          \
        2, { "1111", "2222" }                                                  \
    }
#define pg9r4_2                                                                \
    {                                                                          \
        2, { "1122", "2211" }                                                  \
    }
#define pg9r4_3                                                                \
    {                                                                          \
        2, { "1133", "2233" }                                                  \
    }
#define pg9r4_4                                                                \
    {                                                                          \
        2, { "3311", "3322" }                                                  \
    }
#define pg9r4_5                                                                \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg9r4_6                                                                \
    {                                                                          \
        2, { "2323", "1313" }                                                  \
    }
#define pg9r4_7                                                                \
    {                                                                          \
        2, { "3131", "3232" }                                                  \
    }
#define pg9r4_8                                                                \
    {                                                                          \
        2, { "1212", "2121" }                                                  \
    }
#define pg9r4_9                                                                \
    {                                                                          \
        2, { "2332", "1331" }                                                  \
    }
#define pg9r4_10                                                               \
    {                                                                          \
        2, { "3113", "3223" }                                                  \
    }
#define pg9r4_11                                                               \
    {                                                                          \
        2, { "1221", "2112" }                                                  \
    }
#define pg9r4_12                                                               \
    {                                                                          \
        2, { "2331", "-1332" }                                                 \
    }
#define pg9r4_13                                                               \
    {                                                                          \
        2, { "3223", "-3213" }                                                 \
    }
#define pg9r4_14                                                               \
    {                                                                          \
        2, { "2313", "-1323" }                                                 \
    }
#define pg9r4_15                                                               \
    {                                                                          \
        2, { "3132", "-3231" }                                                 \
    }
#define pg9r4_16                                                               \
    {                                                                          \
        2, { "1112", "-2221" }                                                 \
    }
#define pg9r4_17                                                               \
    {                                                                          \
        2, { "1121", "-2212" }                                                 \
    }
#define pg9r4_18                                                               \
    {                                                                          \
        2, { "3312", "-3321" }                                                 \
    }
#define pg9r4_19                                                               \
    {                                                                          \
        2, { "1211", "-2122" }                                                 \
    }
#define pg9r4_20                                                               \
    {                                                                          \
        2, { "1222", "-2111" }                                                 \
    }
#define pg9r4_21                                                               \
    {                                                                          \
        2, { "1233", "-2133" }                                                 \
    }
// 11: 4/m
#define pg11r4                                                                 \
    {                                                                          \
        41, 21, 21,                                                            \
        {                                                                      \
            pg9r4_1, pg9r4_2, pg9r4_3, pg9r4_4, pg9r4_5, pg9r4_6, pg9r4_7,     \
                pg9r4_8, pg9r4_9, pg9r4_10, pg9r4_11, pg9r4_12, pg9r4_13,      \
                pg9r4_14, pg9r4_15, pg9r4_16, pg9r4_17, pg9r4_18, pg9r4_19,    \
                pg9r4_20, pg9r4_21                                             \
        }                                                                      \
    }
#define pg11r4_constrain empty_constrain
// 10: \bar{4}
#define pg10r4                                                                 \
    {                                                                          \
        41, 21, 21,                                                            \
        {                                                                      \
            pg9r4_1, pg9r4_2, pg9r4_3, pg9r4_4, pg9r4_5, pg9r4_6, pg9r4_7,     \
                pg9r4_8, pg9r4_9, pg9r4_10, pg9r4_11, pg9r4_12, pg9r4_13,      \
                pg9r4_14, pg9r4_15, pg9r4_16, pg9r4_17, pg9r4_18, pg9r4_19,    \
                pg9r4_20, pg9r4_21                                             \
        }                                                                      \
    }
#define pg10r4_constrain empty_constrain
// 9: 4
#define pg9r4                                                                  \
    {                                                                          \
        41, 21, 21,                                                            \
        {                                                                      \
            pg9r4_1, pg9r4_2, pg9r4_3, pg9r4_4, pg9r4_5, pg9r4_6, pg9r4_7,     \
                pg9r4_8, pg9r4_9, pg9r4_10, pg9r4_11, pg9r4_12, pg9r4_13,      \
                pg9r4_14, pg9r4_15, pg9r4_16, pg9r4_17, pg9r4_18, pg9r4_19,    \
                pg9r4_20, pg9r4_21                                             \
        }                                                                      \
    }
#define pg9r4_constrain empty_constrain

// 6,7,8, 1.1.4.9.3, 21 independent components
#define pg6r4_1                                                                \
    {                                                                          \
        1, { "1111" }                                                          \
    }
#define pg6r4_2                                                                \
    {                                                                          \
        1, { "1122" }                                                          \
    }
#define pg6r4_3                                                                \
    {                                                                          \
        1, { "1133" }                                                          \
    }
#define pg6r4_4                                                                \
    {                                                                          \
        1, { "2211" }                                                          \
    }
#define pg6r4_5                                                                \
    {                                                                          \
        1, { "2222" }                                                          \
    }
#define pg6r4_6                                                                \
    {                                                                          \
        1, { "2233" }                                                          \
    }
#define pg6r4_7                                                                \
    {                                                                          \
        1, { "3311" }                                                          \
    }
#define pg6r4_8                                                                \
    {                                                                          \
        1, { "3322" }                                                          \
    }
#define pg6r4_9                                                                \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg6r4_10                                                               \
    {                                                                          \
        1, { "2323" }                                                          \
    }
#define pg6r4_11                                                               \
    {                                                                          \
        1, { "3131" }                                                          \
    }
#define pg6r4_12                                                               \
    {                                                                          \
        1, { "1212" }                                                          \
    }
#define pg6r4_13                                                               \
    {                                                                          \
        1, { "2332" }                                                          \
    }
#define pg6r4_14                                                               \
    {                                                                          \
        1, { "3113" }                                                          \
    }
#define pg6r4_15                                                               \
    {                                                                          \
        1, { "1221" }                                                          \
    }
#define pg6r4_16                                                               \
    {                                                                          \
        1, { "3223" }                                                          \
    }
#define pg6r4_17                                                               \
    {                                                                          \
        1, { "1331" }                                                          \
    }
#define pg6r4_18                                                               \
    {                                                                          \
        1, { "2112" }                                                          \
    }
#define pg6r4_19                                                               \
    {                                                                          \
        1, { "3232" }                                                          \
    }
#define pg6r4_20                                                               \
    {                                                                          \
        1, { "1313" }                                                          \
    }
#define pg6r4_21                                                               \
    {                                                                          \
        1, { "3232" }                                                          \
    }
// 8: mmm
#define pg8r4                                                                  \
    {                                                                          \
        21, 21, 21,                                                            \
        {                                                                      \
            pg6r4_1, pg6r4_2, pg6r4_3, pg6r4_4, pg6r4_5, pg6r4_6, pg6r4_7,     \
                pg6r4_8, pg6r4_9, pg6r4_10, pg6r4_11, pg6r4_12, pg6r4_13,      \
                pg6r4_14, pg6r4_15, pg6r4_16, pg6r4_17, pg6r4_18, pg6r4_19,    \
                pg6r4_20, pg6r4_21                                             \
        }                                                                      \
    }
#define pg8r4_constrain empty_constrain
// 7: mm2
#define pg7r4                                                                  \
    {                                                                          \
        21, 21, 21,                                                            \
        {                                                                      \
            pg6r4_1, pg6r4_2, pg6r4_3, pg6r4_4, pg6r4_5, pg6r4_6, pg6r4_7,     \
                pg6r4_8, pg6r4_9, pg6r4_10, pg6r4_11, pg6r4_12, pg6r4_13,      \
                pg6r4_14, pg6r4_15, pg6r4_16, pg6r4_17, pg6r4_18, pg6r4_19,    \
                pg6r4_20, pg6r4_21                                             \
        }                                                                      \
    }
#define pg7r4_constrain empty_constrain
// 6: 222
#define pg6r4                                                                  \
    {                                                                          \
        21, 21, 21,                                                            \
        {                                                                      \
            pg6r4_1, pg6r4_2, pg6r4_3, pg6r4_4, pg6r4_5, pg6r4_6, pg6r4_7,     \
                pg6r4_8, pg6r4_9, pg6r4_10, pg6r4_11, pg6r4_12, pg6r4_13,      \
                pg6r4_14, pg6r4_15, pg6r4_16, pg6r4_17, pg6r4_18, pg6r4_19,    \
                pg6r4_20, pg6r4_21                                             \
        }                                                                      \
    }
#define pg6r4_constrain empty_constrain

// 3, 4, 5, 1.1.4.9.2, 41 independent components
#define pg3r4_1                                                                \
    {                                                                          \
        1, { "1111" }                                                          \
    }
#define pg3r4_2                                                                \
    {                                                                          \
        1, { "1122" }                                                          \
    }
#define pg3r4_3                                                                \
    {                                                                          \
        1, { "1133" }                                                          \
    }
#define pg3r4_4                                                                \
    {                                                                          \
        1, { "2211" }                                                          \
    }
#define pg3r4_5                                                                \
    {                                                                          \
        1, { "2222" }                                                          \
    }
#define pg3r4_6                                                                \
    {                                                                          \
        1, { "2233" }                                                          \
    }
#define pg3r4_7                                                                \
    {                                                                          \
        1, { "3311" }                                                          \
    }
#define pg3r4_8                                                                \
    {                                                                          \
        1, { "3322" }                                                          \
    }
#define pg3r4_9                                                                \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg3r4_10                                                               \
    {                                                                          \
        1, { "2323" }                                                          \
    }
#define pg3r4_11                                                               \
    {                                                                          \
        1, { "3131" }                                                          \
    }
#define pg3r4_12                                                               \
    {                                                                          \
        1, { "1212" }                                                          \
    }
#define pg3r4_13                                                               \
    {                                                                          \
        1, { "2332" }                                                          \
    }
#define pg3r4_14                                                               \
    {                                                                          \
        1, { "3113" }                                                          \
    }
#define pg3r4_15                                                               \
    {                                                                          \
        1, { "1221" }                                                          \
    }
#define pg3r4_16                                                               \
    {                                                                          \
        1, { "3223" }                                                          \
    }
#define pg3r4_17                                                               \
    {                                                                          \
        1, { "1331" }                                                          \
    }
#define pg3r4_18                                                               \
    {                                                                          \
        1, { "2112" }                                                          \
    }
#define pg3r4_19                                                               \
    {                                                                          \
        1, { "3232" }                                                          \
    }
#define pg3r4_20                                                               \
    {                                                                          \
        1, { "1313" }                                                          \
    }
#define pg3r4_21                                                               \
    {                                                                          \
        1, { "3232" }                                                          \
    }
#define pg3r4_22                                                               \
    {                                                                          \
        1, { "1131" }                                                          \
    }
#define pg3r4_23                                                               \
    {                                                                          \
        1, { "2231" }                                                          \
    }
#define pg3r4_24                                                               \
    {                                                                          \
        1, { "3331" }                                                          \
    }
#define pg3r4_25                                                               \
    {                                                                          \
        1, { "1113" }                                                          \
    }
#define pg3r4_26                                                               \
    {                                                                          \
        1, { "2213" }                                                          \
    }
#define pg3r4_27                                                               \
    {                                                                          \
        1, { "3313" }                                                          \
    }
#define pg3r4_28                                                               \
    {                                                                          \
        1, { "3111" }                                                          \
    }
#define pg3r4_29                                                               \
    {                                                                          \
        1, { "3122" }                                                          \
    }
#define pg3r4_30                                                               \
    {                                                                          \
        1, { "3133" }                                                          \
    }
#define pg3r4_31                                                               \
    {                                                                          \
        1, { "1311" }                                                          \
    }
#define pg3r4_32                                                               \
    {                                                                          \
        1, { "1322" }                                                          \
    }
#define pg3r4_33                                                               \
    {                                                                          \
        1, { "1333" }                                                          \
    }
#define pg3r4_34                                                               \
    {                                                                          \
        1, { "2313" }                                                          \
    }
#define pg3r4_35                                                               \
    {                                                                          \
        1, { "1223" }                                                          \
    }
#define pg3r4_36                                                               \
    {                                                                          \
        1, { "2321" }                                                          \
    }
#define pg3r4_37                                                               \
    {                                                                          \
        1, { "1232" }                                                          \
    }
#define pg3r4_38                                                               \
    {                                                                          \
        1, { "3212" }                                                          \
    }
#define pg3r4_39                                                               \
    {                                                                          \
        1, { "2123" }                                                          \
    }
#define pg3r4_40                                                               \
    {                                                                          \
        1, { "3221" }                                                          \
    }
#define pg3r4_41                                                               \
    {                                                                          \
        1, { "2132" }                                                          \
    }
// 5: 2/m
#define pg5r4                                                                  \
    {                                                                          \
        41, 41, 41,                                                            \
        {                                                                      \
            pg3r4_1, pg3r4_2, pg3r4_3, pg3r4_4, pg3r4_5, pg3r4_6, pg3r4_7,     \
                pg3r4_8, pg3r4_9, pg3r4_10, pg3r4_11, pg3r4_12, pg3r4_13,      \
                pg3r4_14, pg3r4_15, pg3r4_16, pg3r4_17, pg3r4_18, pg3r4_19,    \
                pg3r4_20, pg3r4_21, pg3r4_22, pg3r4_23, pg3r4_24, pg3r4_25,    \
                pg3r4_26, pg3r4_27, pg3r4_28, pg3r4_29, pg3r4_30, pg3r4_31,    \
                pg3r4_32, pg3r4_33, pg3r4_34, pg3r4_35, pg3r4_36, pg3r4_37,    \
                pg3r4_38, pg3r4_39, pg3r4_40, pg3r4_41                         \
        }                                                                      \
    }
#define pg5r4_constrain empty_constrain
// 4: m
#define pg4r4                                                                  \
    {                                                                          \
        41, 41, 41,                                                            \
        {                                                                      \
            pg3r4_1, pg3r4_2, pg3r4_3, pg3r4_4, pg3r4_5, pg3r4_6, pg3r4_7,     \
                pg3r4_8, pg3r4_9, pg3r4_10, pg3r4_11, pg3r4_12, pg3r4_13,      \
                pg3r4_14, pg3r4_15, pg3r4_16, pg3r4_17, pg3r4_18, pg3r4_19,    \
                pg3r4_20, pg3r4_21, pg3r4_22, pg3r4_23, pg3r4_24, pg3r4_25,    \
                pg3r4_26, pg3r4_27, pg3r4_28, pg3r4_29, pg3r4_30, pg3r4_31,    \
                pg3r4_32, pg3r4_33, pg3r4_34, pg3r4_35, pg3r4_36, pg3r4_37,    \
                pg3r4_38, pg3r4_39, pg3r4_40, pg3r4_41                         \
        }                                                                      \
    }
#define pg4r4_constrain empty_constrain
// 3: 2
#define pg3r4                                                                  \
    {                                                                          \
        41, 41, 41,                                                            \
        {                                                                      \
            pg3r4_1, pg3r4_2, pg3r4_3, pg3r4_4, pg3r4_5, pg3r4_6, pg3r4_7,     \
                pg3r4_8, pg3r4_9, pg3r4_10, pg3r4_11, pg3r4_12, pg3r4_13,      \
                pg3r4_14, pg3r4_15, pg3r4_16, pg3r4_17, pg3r4_18, pg3r4_19,    \
                pg3r4_20, pg3r4_21, pg3r4_22, pg3r4_23, pg3r4_24, pg3r4_25,    \
                pg3r4_26, pg3r4_27, pg3r4_28, pg3r4_29, pg3r4_30, pg3r4_31,    \
                pg3r4_32, pg3r4_33, pg3r4_34, pg3r4_35, pg3r4_36, pg3r4_37,    \
                pg3r4_38, pg3r4_39, pg3r4_40, pg3r4_41                         \
        }                                                                      \
    }
#define pg3r4_constrain empty_constrain

// 1, 2, 1.1.4.9.1, 81 independent components
#define pg1r4_1                                                                \
    {                                                                          \
        1, { "1111" }                                                          \
    }
#define pg1r4_2                                                                \
    {                                                                          \
        1, { "1122" }                                                          \
    }
#define pg1r4_3                                                                \
    {                                                                          \
        1, { "1133" }                                                          \
    }
#define pg1r4_4                                                                \
    {                                                                          \
        1, { "2211" }                                                          \
    }
#define pg1r4_5                                                                \
    {                                                                          \
        1, { "2222" }                                                          \
    }
#define pg1r4_6                                                                \
    {                                                                          \
        1, { "2233" }                                                          \
    }
#define pg1r4_7                                                                \
    {                                                                          \
        1, { "3311" }                                                          \
    }
#define pg1r4_8                                                                \
    {                                                                          \
        1, { "3322" }                                                          \
    }
#define pg1r4_9                                                                \
    {                                                                          \
        1, { "3333" }                                                          \
    }
#define pg1r4_10                                                               \
    {                                                                          \
        1, { "1123" }                                                          \
    }
#define pg1r4_11                                                               \
    {                                                                          \
        1, { "1131" }                                                          \
    }
#define pg1r4_12                                                               \
    {                                                                          \
        1, { "1112" }                                                          \
    }
#define pg1r4_13                                                               \
    {                                                                          \
        1, { "2223" }                                                          \
    }
#define pg1r4_14                                                               \
    {                                                                          \
        1, { "2231" }                                                          \
    }
#define pg1r4_15                                                               \
    {                                                                          \
        1, { "2212" }                                                          \
    }
#define pg1r4_16                                                               \
    {                                                                          \
        1, { "3323" }                                                          \
    }
#define pg1r4_17                                                               \
    {                                                                          \
        1, { "3331" }                                                          \
    }
#define pg1r4_18                                                               \
    {                                                                          \
        1, { "3312" }                                                          \
    }
#define pg1r4_19                                                               \
    {                                                                          \
        1, { "1132" }                                                          \
    }
#define pg1r4_20                                                               \
    {                                                                          \
        1, { "1113" }                                                          \
    }
#define pg1r4_21                                                               \
    {                                                                          \
        1, { "1121" }                                                          \
    }
#define pg1r4_22                                                               \
    {                                                                          \
        1, { "2232" }                                                          \
    }
#define pg1r4_23                                                               \
    {                                                                          \
        1, { "2213" }                                                          \
    }
#define pg1r4_24                                                               \
    {                                                                          \
        1, { "2221" }                                                          \
    }
#define pg1r4_25                                                               \
    {                                                                          \
        1, { "3332" }                                                          \
    }
#define pg1r4_26                                                               \
    {                                                                          \
        1, { "3313" }                                                          \
    }
#define pg1r4_27                                                               \
    {                                                                          \
        1, { "3321" }                                                          \
    }
#define pg1r4_28                                                               \
    {                                                                          \
        1, { "2311" }                                                          \
    }
#define pg1r4_29                                                               \
    {                                                                          \
        1, { "2322" }                                                          \
    }
#define pg1r4_30                                                               \
    {                                                                          \
        1, { "2333" }                                                          \
    }
#define pg1r4_31                                                               \
    {                                                                          \
        1, { "3111" }                                                          \
    }
#define pg1r4_32                                                               \
    {                                                                          \
        1, { "3122" }                                                          \
    }
#define pg1r4_33                                                               \
    {                                                                          \
        1, { "3133" }                                                          \
    }
#define pg1r4_34                                                               \
    {                                                                          \
        1, { "1211" }                                                          \
    }
#define pg1r4_35                                                               \
    {                                                                          \
        1, { "1222" }                                                          \
    }
#define pg1r4_36                                                               \
    {                                                                          \
        1, { "1233" }                                                          \
    } //
#define pg1r4_37                                                               \
    {                                                                          \
        1, { "2323" }                                                          \
    }
#define pg1r4_38                                                               \
    {                                                                          \
        1, { "2331" }                                                          \
    }
#define pg1r4_39                                                               \
    {                                                                          \
        1, { "2312" }                                                          \
    }
#define pg1r4_40                                                               \
    {                                                                          \
        1, { "3123" }                                                          \
    }
#define pg1r4_41                                                               \
    {                                                                          \
        1, { "3131" }                                                          \
    }
#define pg1r4_42                                                               \
    {                                                                          \
        1, { "3112" }                                                          \
    }
#define pg1r4_43                                                               \
    {                                                                          \
        1, { "1223" }                                                          \
    }
#define pg1r4_44                                                               \
    {                                                                          \
        1, { "1231" }                                                          \
    }
#define pg1r4_45                                                               \
    {                                                                          \
        1, { "1212" }                                                          \
    }
#define pg1r4_46                                                               \
    {                                                                          \
        1, { "2332" }                                                          \
    }
#define pg1r4_47                                                               \
    {                                                                          \
        1, { "2313" }                                                          \
    }
#define pg1r4_48                                                               \
    {                                                                          \
        1, { "2321" }                                                          \
    }
#define pg1r4_49                                                               \
    {                                                                          \
        1, { "3132" }                                                          \
    }
#define pg1r4_50                                                               \
    {                                                                          \
        1, { "3113" }                                                          \
    }
#define pg1r4_51                                                               \
    {                                                                          \
        1, { "3121" }                                                          \
    }
#define pg1r4_52                                                               \
    {                                                                          \
        1, { "1232" }                                                          \
    }
#define pg1r4_53                                                               \
    {                                                                          \
        1, { "1213" }                                                          \
    }
#define pg1r4_54                                                               \
    {                                                                          \
        1, { "1221" }                                                          \
    } //
#define pg1r4_55                                                               \
    {                                                                          \
        1, { "3211" }                                                          \
    }
#define pg1r4_56                                                               \
    {                                                                          \
        1, { "3222" }                                                          \
    }
#define pg1r4_57                                                               \
    {                                                                          \
        1, { "3233" }                                                          \
    }
#define pg1r4_58                                                               \
    {                                                                          \
        1, { "1311" }                                                          \
    }
#define pg1r4_59                                                               \
    {                                                                          \
        1, { "1322" }                                                          \
    }
#define pg1r4_60                                                               \
    {                                                                          \
        1, { "1333" }                                                          \
    }
#define pg1r4_61                                                               \
    {                                                                          \
        1, { "2111" }                                                          \
    }
#define pg1r4_62                                                               \
    {                                                                          \
        1, { "2122" }                                                          \
    }
#define pg1r4_63                                                               \
    {                                                                          \
        1, { "2133" }                                                          \
    } //
#define pg1r4_64                                                               \
    {                                                                          \
        1, { "3223" }                                                          \
    }
#define pg1r4_65                                                               \
    {                                                                          \
        1, { "3231" }                                                          \
    }
#define pg1r4_66                                                               \
    {                                                                          \
        1, { "3212" }                                                          \
    }
#define pg1r4_67                                                               \
    {                                                                          \
        1, { "1323" }                                                          \
    }
#define pg1r4_68                                                               \
    {                                                                          \
        1, { "1331" }                                                          \
    }
#define pg1r4_69                                                               \
    {                                                                          \
        1, { "1312" }                                                          \
    }
#define pg1r4_70                                                               \
    {                                                                          \
        1, { "2123" }                                                          \
    }
#define pg1r4_71                                                               \
    {                                                                          \
        1, { "2131" }                                                          \
    }
#define pg1r4_72                                                               \
    {                                                                          \
        1, { "2112" }                                                          \
    }
#define pg1r4_73                                                               \
    {                                                                          \
        1, { "3232" }                                                          \
    }
#define pg1r4_74                                                               \
    {                                                                          \
        1, { "3213" }                                                          \
    }
#define pg1r4_75                                                               \
    {                                                                          \
        1, { "3221" }                                                          \
    }
#define pg1r4_76                                                               \
    {                                                                          \
        1, { "1332" }                                                          \
    }
#define pg1r4_77                                                               \
    {                                                                          \
        1, { "1313" }                                                          \
    }
#define pg1r4_78                                                               \
    {                                                                          \
        1, { "1321" }                                                          \
    }
#define pg1r4_79                                                               \
    {                                                                          \
        1, { "2132" }                                                          \
    }
#define pg1r4_80                                                               \
    {                                                                          \
        1, { "2113" }                                                          \
    }
#define pg1r4_81                                                               \
    {                                                                          \
        1, { "2121" }                                                          \
    }
// 2: \bar{1}
#define pg2r4                                                                  \
    {                                                                          \
        81, 81, 81,                                                            \
        {                                                                      \
            pg1r4_1, pg1r4_2, pg1r4_3, pg1r4_4, pg1r4_5, pg1r4_6, pg1r4_7,     \
                pg1r4_8, pg1r4_9, pg1r4_10, pg1r4_11, pg1r4_12, pg1r4_13,      \
                pg1r4_14, pg1r4_15, pg1r4_16, pg1r4_17, pg1r4_18, pg1r4_19,    \
                pg1r4_20, pg1r4_21, pg1r4_22, pg1r4_23, pg1r4_24, pg1r4_25,    \
                pg1r4_26, pg1r4_27, pg1r4_28, pg1r4_29, pg1r4_30, pg1r4_31,    \
                pg1r4_32, pg1r4_33, pg1r4_34, pg1r4_35, pg1r4_36, pg1r4_37,    \
                pg1r4_38, pg1r4_39, pg1r4_40, pg1r4_41, pg1r4_42, pg1r4_43,    \
                pg1r4_44, pg1r4_45, pg1r4_46, pg1r4_47, pg1r4_48, pg1r4_49,    \
                pg1r4_50, pg1r4_51, pg1r4_52, pg1r4_53, pg1r4_54, pg1r4_55,    \
                pg1r4_56, pg1r4_57, pg1r4_58, pg1r4_59, pg1r4_60, pg1r4_61,    \
                pg1r4_62, pg1r4_63, pg1r4_64, pg1r4_65, pg1r4_66, pg1r4_67,    \
                pg1r4_68, pg1r4_69, pg1r4_70, pg1r4_71, pg1r4_72, pg1r4_73,    \
                pg1r4_74, pg1r4_75, pg1r4_76, pg1r4_77, pg1r4_78, pg1r4_79,    \
                pg1r4_80, pg1r4_81                                             \
        }                                                                      \
    }
#define pg2r4_constrain empty_constrain
// 1: 1
#define pg1r4                                                                  \
    {                                                                          \
        81, 81, 81,                                                            \
        {                                                                      \
            pg1r4_1, pg1r4_2, pg1r4_3, pg1r4_4, pg1r4_5, pg1r4_6, pg1r4_7,     \
                pg1r4_8, pg1r4_9, pg1r4_10, pg1r4_11, pg1r4_12, pg1r4_13,      \
                pg1r4_14, pg1r4_15, pg1r4_16, pg1r4_17, pg1r4_18, pg1r4_19,    \
                pg1r4_20, pg1r4_21, pg1r4_22, pg1r4_23, pg1r4_24, pg1r4_25,    \
                pg1r4_26, pg1r4_27, pg1r4_28, pg1r4_29, pg1r4_30, pg1r4_31,    \
                pg1r4_32, pg1r4_33, pg1r4_34, pg1r4_35, pg1r4_36, pg1r4_37,    \
                pg1r4_38, pg1r4_39, pg1r4_40, pg1r4_41, pg1r4_42, pg1r4_43,    \
                pg1r4_44, pg1r4_45, pg1r4_46, pg1r4_47, pg1r4_48, pg1r4_49,    \
                pg1r4_50, pg1r4_51, pg1r4_52, pg1r4_53, pg1r4_54, pg1r4_55,    \
                pg1r4_56, pg1r4_57, pg1r4_58, pg1r4_59, pg1r4_60, pg1r4_61,    \
                pg1r4_62, pg1r4_63, pg1r4_64, pg1r4_65, pg1r4_66, pg1r4_67,    \
                pg1r4_68, pg1r4_69, pg1r4_70, pg1r4_71, pg1r4_72, pg1r4_73,    \
                pg1r4_74, pg1r4_75, pg1r4_76, pg1r4_77, pg1r4_78, pg1r4_79,    \
                pg1r4_80, pg1r4_81                                             \
        }                                                                      \
    }
#define pg1r4_constrain empty_constrain

PointGroup PGRank4[32] = {
    pg1r4,  pg2r4,  pg3r4,  pg4r4,  pg5r4,  pg6r4,  pg7r4,  pg8r4,
    pg9r4,  pg10r4, pg11r4, pg12r4, pg13r4, pg14r4, pg15r4, pg16r4,
    pg17r4, pg18r4, pg19r4, pg20r4, pg21r4, pg22r4, pg23r4, pg24r4,
    pg25r4, pg26r4, pg27r4, pg28r4, pg29r4, pg30r4, pg31r4, pg32r4};

PGConstrain PGRank4Constrain[32] = {
    pg1r4_constrain,  pg2r4_constrain,  pg3r4_constrain,  pg4r4_constrain,
    pg5r4_constrain,  pg6r4_constrain,  pg7r4_constrain,  pg8r4_constrain,
    pg9r4_constrain,  pg10r4_constrain, pg11r4_constrain, pg12r4_constrain,
    pg13r4_constrain, pg14r4_constrain, pg15r4_constrain, pg16r4_constrain,
    pg17r4_constrain, pg18r4_constrain, pg19r4_constrain, pg20r4_constrain,
    pg21r4_constrain, pg22r4_constrain, pg23r4_constrain, pg24r4_constrain,
    pg25r4_constrain, pg26r4_constrain, pg27r4_constrain, pg28r4_constrain,
    pg29r4_constrain, pg30r4_constrain, pg31r4_constrain, pg32r4_constrain};

// PointGroup PGRank2[32] = {
//     {81,81,81,PointGroup28rank4},
//     {81,81,81,PointGroup28rank4},
//     {41,41,41,PointGroup28rank4},
//     {41,41,41,PointGroup28rank4},
//     {41,41,41,PointGroup28rank4},
//     {21,21,21,PointGroup28rank4},
//     {21,21,21,PointGroup28rank4},
//     {21,21,21,PointGroup28rank4},
//     {41,21,21,PointGroup28rank4},
//     {41,21,21,PointGroup28rank4},
//     {41,21,21,PointGroup28rank4},
//     {21,11,11,PointGroup28rank4},
//     {21,11,11,PointGroup28rank4},
//     {21,11,11,PointGroup28rank4},
//     {21,11,11,PointGroup28rank4},
//     {73,31,27,PointGroup28rank4},
//     {73,31,27,PointGroup28rank4},
//     {37,16,14,PointGroup28rank4},
//     {37,16,14,PointGroup28rank4},
//     {37,16,14,PointGroup28rank4},
//     {41,23,19,PointGroup28rank4},
//     {41,23,19,PointGroup28rank4},
//     {41,23,19,PointGroup28rank4},
//     {21,12,10,PointGroup28rank4},
//     {21,12,10,PointGroup28rank4},
//     {21,12,10,PointGroup28rank4},
//     {21,12,10,PointGroup28rank4},
//     {21,7,7,PointGroup28rank4},
//     {21,7,7,PointGroup29rank4},
//     {21,4,4,PointGroup30rank4},
//     {21,4,4,PointGroup31rank4},
//     {21,4,4,PointGroup32rank4},
// };