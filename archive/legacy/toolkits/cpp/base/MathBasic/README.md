#mathbasic

## Dependencies

| Software   | Version | Url                                                                       |
| ---------- | :-----: | ------------------------------------------------------------------------- |
| ntextutils |  0.1.1  | git@e.coding.net:sijin/research-code-commercialization/text-utilities.git |
| zf_log     |         | https://github.com/billcxx/zf_log.git                                     |

From gitee 3adda4881cae6b883df0d4f67918777e87be022d 2021 Jun 18 16:24
在 C 中生成真正的多维数组，方便与 fortran 联合调用。无 GUI，无 main，纯 lib 使用

1. 2D, 3D, 4D 数组
2. vector, matrix 的操作
3. 坐标变换
4. exprtk，从字符串得到数学公式
5. lapack
6. 常数

## Array Usage

```C
double(*kx)[kdim[0]][kdim[1]][kdim[2]];
n_data_3D_double_init(kdim[0], kdim[1], kdim[2], &kx);
```

Use \*kx when passing the array to other functions, use (\*kx) when using the array within current scope.

## On Linux

## On Windows

## On mac

CC=gcc-10 meson builddir
export LIBRARY_PATH=/Library/Developer/CommandLineTools/SDKs/MacOSX11.1.sdk/usr/lib/:/usr/local/Cellar/gcc/10.2.0/lib/gcc/10

source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..
