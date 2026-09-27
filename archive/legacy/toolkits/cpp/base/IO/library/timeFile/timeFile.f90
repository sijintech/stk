module niobasic_timeFile
    use iso_c_binding
    use,intrinsic::iso_fortran_env
    implicit none
    interface
        subroutine n_timeFile_write_line_from_double_c(input,length,filename) bind(c,name="n_timeFile_write_line_from_double_f")
            use,intrinsic :: iso_c_binding, only:c_char,c_double,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename
            integer(kind=c_int),intent(in) :: length
            type(c_ptr) :: input
        end subroutine n_timeFile_write_line_from_double_c

        subroutine n_timeFile_write_line_from_string_c(header,filename) bind(c,name="n_timeFile_write_line_from_string_f")
            use,intrinsic :: iso_c_binding, only:c_char,c_double,c_int,c_ptr
            character(kind=c_char),intent(in),dimension(*) :: filename,header
        end subroutine n_timeFile_write_line_from_string_c        
    end interface
    contains
    subroutine n_timeFile_write_line_from_double(input,filename)
        use,intrinsic :: iso_c_binding, only:c_ptr
        implicit none
        real(kind=real64),intent(in),target::input(:)
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c
        type(c_ptr) :: input_c
        filename_c=filename//char(0)
        input_c=c_loc(input)
        call n_timeFile_write_line_from_double_c(input_c,size(input),filename_c)
    end subroutine

    subroutine n_timeFile_write_line_from_string(input,filename)
        implicit none
        character(len=*),intent(in) ::input
        character(len=*),intent(in) :: filename
        character(len=100) :: filename_c,input_c
        filename_c=filename//char(0)
        input_c=input//char(0)
        call n_timeFile_write_line_from_string_c(input_c,filename_c)

    end subroutine
end module