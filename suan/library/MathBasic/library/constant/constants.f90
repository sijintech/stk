module nmathbasic_constants
    use, intrinsic :: ISO_Fortran_env
    use iso_c_binding
    implicit none
    integer, parameter::idp = int64
    integer, parameter::rdp = real64
    integer, parameter::cdp = 8

    ! real(c_double), bind(C, name="NPI") :: npi
    ! real(c_double), bind(C, name="NDEG2RAD") :: ndeg2rad
    ! real(c_double), bind(C, name="NRAD2DEG") :: nrad2deg
    ! real(c_double), bind(C, name="NEPSILON0") :: nepsilon0
    ! real(c_double), bind(C, name="NZEROTHRESHOLD") :: nzerothreshold

    real(kind=rdp),parameter :: npi = 3.141592653589793238462643383279502884197169399375105820974944592307816
    real(kind=rdp),parameter :: ndeg2rad = 0.0174532925199432957692369076848861271344287188854172545609719144
    real(kind=rdp),parameter :: nrad2deg = 57.295779513082320876798154814105170332405472466564321549160243861
    real(kind=rdp),parameter :: nepsilon0 = 8.8541878128d-12
    real(kind=rdp),parameter :: nzerothreshold = 1d-8

end module nmathbasic_constants