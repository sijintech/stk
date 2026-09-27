module niobasic_controlFile
    use iso_c_binding
    use, intrinsic::iso_fortran_env

    interface
        integer(c_int) function n_get_xml_element_as_int_c(filename, xpath, meaning, de) bind(c, name="n_get_xml_element_as_int_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_int
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning
            integer(kind=c_int), intent(in) :: de
        end function n_get_xml_element_as_int_c

   real(c_double) function n_get_xml_element_as_double_c(filename, xpath, meaning, de) bind(c, name="n_get_xml_element_as_double_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_double
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning
            real(kind=c_double), intent(in) :: de
        end function n_get_xml_element_as_double_c

        subroutine n_get_xml_element_as_string_c(output, filename, xpath, meaning, de) bind(c, name="n_get_xml_element_as_string")
            use, intrinsic :: iso_c_binding, only: c_char, c_double
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning, de
            character(kind=c_char), intent(out), dimension(20) :: output
        end subroutine n_get_xml_element_as_string_c

        integer(c_int) function n_get_xml_element_count_c(filename, xpath, meaning) bind(c, name="n_get_xml_element_count")
            use, intrinsic :: iso_c_binding, only: c_char, c_int
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning
        end function n_get_xml_element_count_c

        subroutine n_set_xml_element_by_int_c(input, filename, xpath, meaning) bind(c, name="n_set_xml_element_by_int_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_int
            integer(kind=c_int), intent(in) :: input
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning
        end subroutine n_set_xml_element_by_int_c

        subroutine n_set_xml_element_by_double_c(input, filename, xpath, meaning) bind(c, name="n_set_xml_element_by_double_f")
            use, intrinsic :: iso_c_binding, only: c_char, c_double
            real(kind=c_double), intent(in) :: input
            character(kind=c_char), intent(in), dimension(*) :: filename, xpath, meaning
        end subroutine n_set_xml_element_by_double_c

    end interface
contains

    logical function n_get_xml_element_as_bool(filename, xpath, meaning) result(out)
        character(len=*), intent(in) :: filename, xpath, meaning
        character, dimension(20) :: text
        call n_get_xml_element_as_string_c(text, filename, xpath, meaning, "F")
        if (text(1) .eq. 'T' .or. text(1) .eq. 't') then
            out = .True.
        else
            out = .False.
        end if
    end function

    integer function n_get_xml_element_as_int(filename, xpath, meaning, de) result(out)
        use, intrinsic :: iso_c_binding, only: c_int
        character(len=*), intent(in)::filename, xpath, meaning
        character(len=100) :: filename_c, xpath_c, meaning_c
        integer(kind=int32), intent(in) :: de
        integer(kind=c_int) :: de_c
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        de_c=de
        out = n_get_xml_element_as_int_c(filename_c, xpath_c, meaning_c, de_c)
    end function

    integer function n_get_xml_element_count(filename, xpath, meaning) result(out)
        character(len=*), intent(in)::filename, xpath, meaning
        character(len=100) :: filename_c, xpath_c, meaning_c
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        out = n_get_xml_element_count_c(filename_c, xpath_c, meaning_c)
    end function

    real(kind=real64) function n_get_xml_element_as_double(filename, xpath, meaning, de) result(out)
        use, intrinsic :: iso_c_binding, only: c_double
        character(len=*), intent(in)::filename, xpath, meaning
        character(len=100) :: filename_c, xpath_c, meaning_c
        real(kind=c_double), intent(in) :: de
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        out = n_get_xml_element_as_double_c(filename_c, xpath_c, meaning_c, de)
    end function

    subroutine n_get_xml_element_as_string(output, filename, xpath, meaning, de)
        use, intrinsic :: iso_c_binding, only: c_char
        character(len=*), intent(in)::filename, xpath, meaning, de
        character(len=100) :: filename_c, xpath_c, meaning_c, de_c, output_c
        character(len=*), intent(out) :: output
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        de_c = de//char(0)
        call n_get_xml_element_as_string_c(output_c, filename_c, xpath_c, meaning_c, de_c)
        output = output_c
    end subroutine

    subroutine n_set_xml_element_by_int(input, filename, xpath, meaning)
        use, intrinsic :: iso_c_binding, only: c_char
        character(len=*), intent(in)::filename, xpath, meaning
        character(len=100) :: filename_c, xpath_c, meaning_c
        integer, intent(in) :: input
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        call n_set_xml_element_by_int_c(input, filename_c, xpath_c, meaning_c)
    end subroutine

    subroutine n_set_xml_element_by_double(input, filename, xpath, meaning)
        use, intrinsic :: iso_c_binding, only: c_char
        character(len=*), intent(in)::filename, xpath, meaning
        character(len=100) :: filename_c, xpath_c, meaning_c
        real(kind=8), intent(in) :: input
        filename_c = filename//char(0)
        xpath_c = xpath//char(0)
        meaning_c = meaning//char(0)
        call n_set_xml_element_by_double_c(input, filename_c, xpath_c, meaning_c)
    end subroutine
end module
