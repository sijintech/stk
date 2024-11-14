# suan-pc-effprop

## Dependencies
Be careful, the sequence matters when pulling using cmake
| Software             | Version  | Url                                                                            |
|----------------------|:--------:|--------------------------------------------------------------------------------|
| zf_log               |          | https://github.com/billcxx/zf_log.git                                          |
| ntextutils           |  5f0bdff | git@e.coding.net:sijin/research-code-commercialization/text-utilities.git      |
| nmathbasic           |  822b2d5 | git@e.coding.net:sijin/research-code-commercialization/math-basic.git          |
| niobasic             |  83aa4ff | git@e.coding.net:sijin/research-code-commercialization/io-basic.git            |
| nlicense             |  50a9fa0 | git@e.coding.net:sijin/license/license.git                                     |
| nmathfft             |  d2cdec7 | git@e.coding.net:sijin/research-code-commercialization/math-fft.git            |
| nstructuregenerator  |  d1a5f9c | git@e.coding.net:sijin/research-code-commercialization/structure-generator.git |
| input-form-dimension |  1.1.0   | npmjs                                                                          |
| input-form-structure |  1.5.0   | npmjs                                                                          |
| input-form-phase     |  1.1.1   | npmjs                                                                          |
| input-form-tensor    |  1.1.1   | npmjs                                                                          |
| input-form-output    |  1.2.2   | npmjs                                                                          |
| start-stop-control   |  1.0.0   | npmjs                                                                          |
| output-view-chart    |  1.1.0   | npmjs                                                                          |
| output-view-console  |  1.0.0   | npmjs                                                                          |
| output-view-control  |  1.0.0   | npmjs                                                                          |




#### 介绍
The suan-pc series of simulation program for effective property calculation.

#### 软件架构
软件架构说明

#### 更新步骤
1. 保持core和gui同步，更新core中cmake的版本号
2. 更新gui中package.json 的版本号
3. 更新coding.net中默认变量的版本号
4. 在coding.net中发布新的tag

#### 安装教程

1.  安装meson build
2.  使用meson builddir，meson compile编译程序

1. windows上也是用cmake，但要用ninja generator `cmake -G Ninja ..`
2. 然后使用ninja 编译，`ninja`

yarn build
then use the libtool script


source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..