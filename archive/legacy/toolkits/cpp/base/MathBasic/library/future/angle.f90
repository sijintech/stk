pure function angle(v1,v2)
    use nmathbasic_constants
    implicit none
    real(kind=rdp) :: angle,arg
    real(kind=rdp),intent(in) :: v1(3),v2(3)
    real(kind=rdp),parameter :: pi = dacos(-1.d0)
    arg = dot_product(v1,v2)/(norm2(v1)*norm2(v2))
    angle = acos(max(min(arg,1.d0),-1.d0))
    angle = angle/pi*180
end function
