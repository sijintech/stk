real(kind=rdp) function gaussDistribution(mu,sigma)   !tuy20160504
    use nmathbasic_constants
    implicit none

    real(kind=rdp) mu,sigma
    real(kind=rdp) pi,u1,u2

    pi=dacos(-1.d0)
    !tuy20160504      call random_seed()
    call random_number(u1)
    call random_number(u2)
    gaussDistribution = sqrt(-2.0 * log(u1)) * cos(2.d0 * pi * u2) * sigma + mu   !tuy20160504

    return
end function
