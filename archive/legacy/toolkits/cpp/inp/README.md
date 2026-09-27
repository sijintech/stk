# Abaqus 输入文件解析库 (inp_io)

这个库提供了解析 Abaqus .inp 输入文件的功能，并将其转换成结构化的数据，方便在 C、Fortran 和 Python 等语言中使用。

## 特性

- 完全符合 Abaqus 官方语法规则
- 支持所有 Abaqus 关键字格式
- 支持参数解析、数据行解析和行延续
- 内存安全设计，自动内存管理
- 跨平台支持: Windows, Linux, macOS
- 可在多种编程语言中使用
- 详细的错误报告机制

## 编译指南

### 使用 CMake 构建（推荐）

```bash
# 1. 创建构建目录
mkdir build && cd build

# 2. 配置
cmake ..

# 3. 构建
cmake --build .

# 4. 安装（可选，需要管理员权限）
cmake --install .
```

### 使用 GCC 和 Makefile 构建

```bash
# 编译静态库
make

# 编译并运行测试
make test
make run

# 安装（可选，需要管理员权限）
make install

# 查看更多选项
make help
```

### 手动编译

```bash
# 编译静态库
gcc -c -fPIC inp_io.c -o inp_io.o
ar rcs libinp_io.a inp_io.o

# 编译动态库 (Linux/macOS)
gcc -shared -fPIC inp_io.c -o libinp_io.so

# 编译动态库 (Windows)
gcc -shared -fPIC inp_io.c -o inp_io.dll
```

## 在不同语言中使用

### 在 C 语言中使用

```c
#include "inp_io.h"
#include <stdio.h>

int main() {
    inp_file_t* inp_file = NULL;
    
    // 解析文件
    inp_result_t result = inp_parse_file("model.inp", &inp_file);
    if (result != INP_SUCCESS) {
        printf("解析失败，错误码: %d\n", result);
        return 1;
    }
    
    // 打印文件信息
    inp_print_file_info(inp_file);
    
    // 查找特定关键字
    const inp_keyword_t* material = inp_find_keyword(inp_file, "MATERIAL");
    if (material) {
        printf("找到材料定义，共 %d 个参数\n", material->parameter_count);
        
        // 遍历参数
        for (int i = 0; i < material->parameter_count; i++) {
            if (material->parameters[i].has_value) {
                printf("  %s = %s\n", 
                       material->parameters[i].name, 
                       material->parameters[i].value);
            }
        }
    }
    
    // 释放内存
    inp_free_file(inp_file);
    
    return 0;
}
```

**编译方法:**
```bash
# 静态链接
gcc -o myprogram myprogram.c -I/path/to/include -L/path/to/lib -linp_io

# 动态链接
gcc -o myprogram myprogram.c -I/path/to/include -L/path/to/lib -linp_io
```

### 在 Python 中使用

#### 方法 1: 使用 ctypes 直接调用

```python
import ctypes
import os

# 加载库
lib_path = os.path.join(os.path.dirname(__file__), "libinp_io.so")  # 或 inp_io.dll
inp_io = ctypes.CDLL(lib_path)

# 定义数据结构
class InpParameter(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 80),
        ("value", ctypes.c_char * 256),
        ("has_value", ctypes.c_int)
    ]

class InpDataLine(ctypes.Structure):
    _fields_ = [
        ("content", ctypes.c_char * 256),
        ("fields", ctypes.POINTER(ctypes.c_char_p)),
        ("field_count", ctypes.c_int)
    ]

class InpKeyword(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 80),
        ("parameters", InpParameter * 50),
        ("parameter_count", ctypes.c_int),
        ("data_lines", ctypes.POINTER(InpDataLine)),
        ("data_line_count", ctypes.c_int),
        ("line_number", ctypes.c_int)
    ]

# 使用示例
def parse_inp_file(filepath):
    # 设置返回类型和参数
    inp_io.inp_parse_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    inp_io.inp_parse_file.restype = ctypes.c_int
    
    # 调用解析函数
    file_ptr = ctypes.c_void_p()
    result = inp_io.inp_parse_file(filepath.encode('utf-8'), ctypes.byref(file_ptr))
    
    if result != 0:  # INP_SUCCESS
        print(f"解析失败，错误码: {result}")
        return None
    
    # 处理结果
    # ...
    
    # 释放内存
    inp_io.inp_free_file(file_ptr)
    
    return result

# 使用方法
parse_inp_file("model.inp")
```

#### 方法 2: 使用 SWIG 绑定(需要单独生成绑定代码)

```python
import inp_io

# 解析文件
result, inp_file = inp_io.parse_file("model.inp")

if result == inp_io.INP_SUCCESS:
    # 打印信息
    inp_io.print_file_info(inp_file)
    
    # 查找关键字
    material = inp_io.find_keyword(inp_file, "MATERIAL")
    if material:
        print(f"找到材料定义，共 {material.parameter_count} 个参数")
        
    # 自动内存管理，无需手动释放
```

### 在 Fortran 中使用

#### 创建 Fortran 接口模块

```fortran
! 文件: inp_io_fortran.f90
module inp_io_fortran
  use, intrinsic :: iso_c_binding
  implicit none
  
  ! 复制 C 数据结构定义为 Fortran 类型
  type, bind(C) :: inp_parameter_t
    character(kind=c_char) :: name(80)
    character(kind=c_char) :: value(256)
    integer(c_int) :: has_value
  end type
  
  ! 更多类型定义...
  
  ! C 函数接口定义
  interface
    function inp_parse_file(filepath, result) result(status) bind(C, name="inp_parse_file")
      import :: c_char, c_ptr, c_int
      character(kind=c_char), intent(in) :: filepath(*)
      type(c_ptr), intent(out) :: result
      integer(c_int) :: status
    end function
    
    ! 更多函数接口...
    
    subroutine inp_free_file(file) bind(C, name="inp_free_file")
      import :: c_ptr
      type(c_ptr), value :: file
    end subroutine
  end interface
  
  ! 高级封装函数
  contains
    ! 添加更友好的 Fortran 风格封装...
end module

! 使用示例程序
program test_inp_io
  use inp_io_fortran
  implicit none
  
  type(c_ptr) :: inp_file = c_null_ptr
  integer :: result
  character(len=100) :: filepath = "model.inp"//char(0)  ! 注意添加 C 字符串结束符
  
  ! 解析文件
  result = inp_parse_file(filepath, inp_file)
  
  if (result == 0) then  ! INP_SUCCESS
    print *, "文件解析成功"
    
    ! 这里添加其他处理...
    
    ! 释放内存
    call inp_free_file(inp_file)
  else
    print *, "解析失败，错误码:", result
  endif
  
end program
```

**编译方法:**
```bash
# 编译 Fortran 程序并链接 C 库
gfortran -o fortran_program inp_io_fortran.f90 test_program.f90 -L/path/to/lib -linp_io
```

## 注意事项

1. **内存管理**：
   - C 语言：使用后必须调用 `inp_free_file()` 释放内存
   - Python：使用 ctypes 时需手动释放，使用 SWIG 绑定时自动处理
   - Fortran：必须调用 `inp_free_file()` 释放内存

2. **路径处理**：
   - Windows 平台需注意路径分隔符（推荐使用正斜杠 "/"）
   - 文件路径最好使用绝对路径

3. **错误处理**：
   - 检查函数返回值，确保 result = INP_SUCCESS
   - 错误时记得释放已分配的内存

4. **跨平台编译**：
   - Windows: MinGW 或 MSVC
   - Linux/macOS: GCC 或 Clang

## 许可证

[Your License]

## 联系方式

[Your contact information]
