#text-utilities

From Gitee e6fbdd6baf6afd343c64f72ab93a338a644f63de 2021-08-02 12:28

![Build](https://img.shields.io/endpoint?style=flat-square&url=https%3A%2F%2Fnibiru.llc%2Fjenkinsbuild%2Finfo.php%3Flabel%3DBuild%26name%3Dntextutils)

#### 介绍

ntextutils.h is the core.
ntextutils.hpp is wrapper for C++.

#### Jenkinsfile

Make sure the Jenkins build is successful before making pull request

#### Usage

```
meson build  # only needs to run once
cd build
meson compile
meson test
```

#### Wrap git

```
[wrap-git]
url=https://gitee.com/nibiru-technology/ntextutils.git
revision=meson

[provides]
dependency_names=ntextutils_dep
```

export LIBRARY_PATH=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/usr/lib

source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..
