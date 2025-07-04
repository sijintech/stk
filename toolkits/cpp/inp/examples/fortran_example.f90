! Fortran 使用示例
!
! 此示例展示了如何在 Fortran 程序中使用 inp_io 库
! 解析 Abaqus 输入文件并访问解析后的数据结构。
!
! 编译方法:
! gfortran -o fortran_example fortran_example.f90 -L.. -linp_io

module inp_io_fortran
  use, intrinsic :: iso_c_binding
  implicit none

  ! 结果代码枚举
  integer, parameter :: INP_SUCCESS = 0
  integer, parameter :: INP_ERROR_FILE_NOT_FOUND = -1
  integer, parameter :: INP_ERROR_MEMORY_ALLOCATION = -2
  integer, parameter :: INP_ERROR_INVALID_FORMAT = -3
  integer, parameter :: INP_ERROR_LINE_TOO_LONG = -4
  integer, parameter :: INP_ERROR_INVALID_KEYWORD = -5

  ! 最大值定义
  integer, parameter :: MAX_LINE_LENGTH = 256
  integer, parameter :: MAX_KEYWORD_LENGTH = 80
  integer, parameter :: MAX_PARAM_NAME_LENGTH = 80
  integer, parameter :: MAX_PARAM_VALUE_LENGTH = 256
  integer, parameter :: MAX_PARAMS_PER_KEYWORD = 50

  ! 参数结构体
  type, bind(C) :: inp_parameter_t
    character(kind=c_char) :: name(MAX_PARAM_NAME_LENGTH)
    character(kind=c_char) :: value(MAX_PARAM_VALUE_LENGTH)
    integer(c_int) :: has_value
  end type

  ! 数据行结构体 (简化，不包含字段数组)
  type, bind(C) :: inp_data_line_t
    character(kind=c_char) :: content(MAX_LINE_LENGTH)
    type(c_ptr) :: fields
    integer(c_int) :: field_count
  end type

  ! 关键字结构体
  type, bind(C) :: inp_keyword_t
    character(kind=c_char) :: name(MAX_KEYWORD_LENGTH)
    type(inp_parameter_t) :: parameters(MAX_PARAMS_PER_KEYWORD)
    integer(c_int) :: parameter_count
    type(c_ptr) :: data_lines
    integer(c_int) :: data_line_count
    integer(c_int) :: line_number
  end type

  ! 元数据结构体
  type, bind(C) :: inp_metadata_t
    character(kind=c_char) :: filename(256)
    integer(c_int) :: total_lines
    integer(c_int) :: keyword_count
    integer(c_int) :: comment_lines
    character(kind=c_char) :: parse_errors(1024)
  end type

  ! 文件结构体
  type, bind(C) :: inp_file_t
    type(c_ptr) :: keywords
    integer(c_int) :: keyword_count
    type(inp_metadata_t) :: metadata
  end type

  ! C 函数接口声明
  interface
    ! 解析文件接口
    function inp_parse_file(filepath, result) result(status) bind(C, name="inp_parse_file")
      import :: c_char, c_ptr, c_int
      character(kind=c_char), intent(in) :: filepath(*)
      type(c_ptr), intent(out) :: result
      integer(c_int) :: status
    end function

    ! 释放内存接口
    subroutine inp_free_file(file) bind(C, name="inp_free_file")
      import :: c_ptr
      type(c_ptr), value :: file
    end subroutine

    ! 查找关键字接口
    function inp_find_keyword(file, keyword_name) result(keyword_ptr) bind(C, name="inp_find_keyword")
      import :: c_ptr, c_char
      type(c_ptr), value :: file
      character(kind=c_char), intent(in) :: keyword_name(*)
      type(c_ptr) :: keyword_ptr
    end function

    ! 打印文件信息接口
    subroutine inp_print_file_info(file) bind(C, name="inp_print_file_info")
      import :: c_ptr
      type(c_ptr), value :: file
    end subroutine
  end interface

  ! 实用工具函数
  contains
    ! 转换 C 字符串到 Fortran 字符串
    function c_to_f_string(c_string) result(f_string)
      character(kind=c_char), intent(in) :: c_string(*)
      character(len=:), allocatable :: f_string
      integer :: i, length

      length = 0
      do i = 1, huge(i)-1
        if (c_string(i) == c_null_char) exit
        length = length + 1
      end do

      allocate(character(len=length) :: f_string)
      do i = 1, length
        f_string(i:i) = c_string(i)
      end do
    end function

    ! 转换 Fortran 字符串到 C 字符串(添加末尾的空字符)
    subroutine f_to_c_string(f_string, c_string, max_len)
      character(len=*), intent(in) :: f_string
      character(kind=c_char), intent(out) :: c_string(*)
      integer, intent(in) :: max_len
      integer :: i, length

      length = min(len(f_string), max_len-1)
      
      do i = 1, length
        c_string(i) = f_string(i:i)
      end do
      
      c_string(length+1) = c_null_char
    end subroutine
end module

program fortran_example
  use inp_io_fortran
  use, intrinsic :: iso_c_binding
  implicit none

  ! 局部变量
  type(c_ptr) :: inp_file_ptr = c_null_ptr
  type(c_ptr) :: keyword_ptr = c_null_ptr
  type(inp_keyword_t), pointer :: keyword
  character(len=256) :: filepath
  character(kind=c_char) :: c_filepath(257)
  character(kind=c_char) :: c_keyword_name(81)
  integer :: status, i
  character(len=80) :: arg

  print *, "=== inp_io Fortran 使用示例 ==="

  ! 获取命令行参数
  filepath = "./example.inp" ! 默认文件路径
  if (command_argument_count() > 0) then
    call get_command_argument(1, arg)
    filepath = trim(arg)
  end if

  print *, "解析文件: ", trim(filepath)
  print *

  ! 将Fortran字符串转换为C字符串(以空字符结尾)
  call f_to_c_string(filepath, c_filepath, size(c_filepath))

  ! 解析文件
  status = inp_parse_file(c_filepath, inp_file_ptr)
  
  if (status /= INP_SUCCESS) then
    print *, "解析失败，错误码: ", status
    stop
  end if

  print *, "文件已成功解析!"
  
  ! 打印文件信息
  call inp_print_file_info(inp_file_ptr)
  
  ! 查找材料关键字
  call f_to_c_string("MATERIAL", c_keyword_name, size(c_keyword_name))
  keyword_ptr = inp_find_keyword(inp_file_ptr, c_keyword_name)
  
  if (c_associated(keyword_ptr)) then
    ! 将C指针转换为Fortran指针
    call c_f_pointer(keyword_ptr, keyword)
    
    print *
    print *, "找到材料关键字:"
    print *, "  行号: ", keyword%line_number
    print *, "  参数数量: ", keyword%parameter_count
    
    ! 打印参数
    do i = 1, keyword%parameter_count
      if (keyword%parameters(i)%has_value == 1) then
        print *, "  参数 #", i, ": ", &
            c_to_f_string(keyword%parameters(i)%name), " = ", &
            c_to_f_string(keyword%parameters(i)%value)
      else
        print *, "  参数 #", i, ": ", c_to_f_string(keyword%parameters(i)%name)
      end if
    end do
  else
    print *
    print *, "未找到材料关键字"
  end if
  
  ! 释放内存
  call inp_free_file(inp_file_ptr)
  print *
  print *, "库函数已正确释放内存"

end program fortran_example
