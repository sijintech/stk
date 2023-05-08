module zf_log
    use iso_c_binding
    implicit none
    interface
        subroutine zf_logv_c(text) bind(c, name="zf_logv_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
        subroutine zf_logd_c(text) bind(c, name="zf_logd_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
        subroutine zf_logi_c(text) bind(c, name="zf_logi_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
        subroutine zf_logw_c(text) bind(c, name="zf_logw_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
        subroutine zf_loge_c(text) bind(c, name="zf_loge_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
        subroutine zf_logf_c(text) bind(c, name="zf_logf_f")
            use, intrinsic::iso_c_binding, only: c_char
            character(kind=c_char), intent(in), dimension(*) :: text
        end subroutine
    end interface

contains

    subroutine zf_logv(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_logv_c(text_c)
    end subroutine

    subroutine zf_logd(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_logd_c(text_c)
    end subroutine

    subroutine zf_logi(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_logi_c(text_c)
    end subroutine

    subroutine zf_logw(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_logw_c(text_c)
    end subroutine

    subroutine zf_loge(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_loge_c(text_c)
    end subroutine

    subroutine zf_logf(text)
        use, intrinsic :: iso_c_binding
        implicit none
        character(len=*), intent(in) :: text
        character(len=256) :: text_c
        text_c = text//char(0)
        call zf_logf_c(text_c)
    end subroutine

end module
