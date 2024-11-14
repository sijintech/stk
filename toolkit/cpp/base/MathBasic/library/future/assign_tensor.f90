subroutine assignCubic4thRankTensor(tensor, a11, a12, a44)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(6, 6) :: tensor
    real(kind=rdp), intent(in) :: a11, a12, a44

    tensor(1, 1) = a11; tensor(1, 2) = a12; tensor(1, 3) = a12; tensor(1, 4) = 0.d0; tensor(1, 5) = 0.d0; tensor(1, 6) = 0.d0
    tensor(2, 1) = a12; tensor(2, 2) = a11; tensor(2, 3) = a12; tensor(2, 4) = 0.d0; tensor(2, 5) = 0.d0; tensor(2, 6) = 0.d0
    tensor(3, 1) = a12; tensor(3, 2) = a12; tensor(3, 3) = a11; tensor(3, 4) = 0.d0; tensor(3, 5) = 0.d0; tensor(3, 6) = 0.d0
    tensor(4, 1) = 0.d0; tensor(4, 2) = 0.d0; tensor(4, 3) = 0.d0; tensor(4, 4) = a44; tensor(4, 5) = 0.d0; tensor(4, 6) = 0.d0
    tensor(5, 1) = 0.d0; tensor(5, 2) = 0.d0; tensor(5, 3) = 0.d0; tensor(5, 4) = 0.d0; tensor(5, 5) = a44; tensor(5, 6) = 0.d0
    tensor(6, 1) = 0.d0; tensor(6, 2) = 0.d0; tensor(6, 3) = 0.d0; tensor(6, 4) = 0.d0; tensor(6, 5) = 0.d0; tensor(6, 6) = a44

end subroutine

subroutine assignCubic31RankTensor(tensor, a11, a12, a44)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(3, 18) :: tensor
    real(kind=rdp), intent(in) :: a11, a12, a44

    tensor(1, 1) = a11; tensor(1, 2) = 0.d0; tensor(1, 3) = 0.d0; tensor(1, 4) = a12; tensor(1, 5) = 0.d0; tensor(1, 6) = 0.d0; tensor(1, 7) = a12; tensor(1, 8) = 0.d0; tensor(1, 9) = 0.d0; tensor(1, 10) = 0.d0; tensor(1, 11) = a44; tensor(1, 12) = 0.d0; tensor(1, 13) = 0.d0; tensor(1, 14) = 0.d0; tensor(1, 15) = a44; tensor(1, 16) = 0.d0; tensor(1, 17) = 0.d0; tensor(1, 18) = 0.d0
    tensor(2, 1) = 0.d0; tensor(2, 2) = a12; tensor(2, 3) = 0.d0; tensor(2, 4) = 0.d0; tensor(2, 5) = a11; tensor(2, 6) = 0.d0; tensor(2, 7) = 0.d0; tensor(2, 8) = a12; tensor(2, 9) = 0.d0; tensor(2, 10) = a44; tensor(2, 11) = 0.d0; tensor(2, 12) = 0.d0; tensor(2, 13) = 0.d0; tensor(2, 14) = 0.d0; tensor(2, 15) = 0.d0; tensor(2, 16) = 0.d0; tensor(2, 17) = 0.d0; tensor(2, 18) = a44
    tensor(3, 1) = 0.d0; tensor(3, 2) = 0.d0; tensor(3, 3) = a12; tensor(3, 4) = 0.d0; tensor(3, 5) = 0.d0; tensor(3, 6) = a12; tensor(3, 7) = 0.d0; tensor(3, 8) = 0.d0; tensor(3, 9) = a11; tensor(3, 10) = 0.d0; tensor(3, 11) = 0.d0; tensor(3, 12) = 0.d0; tensor(3, 13) = a44; tensor(3, 14) = 0.d0; tensor(3, 15) = 0.d0; tensor(3, 16) = 0.d0; tensor(3, 17) = a44; tensor(3, 18) = 0.d0

end subroutine

subroutine assignCubic22RankTensor(tensor, a11, a12, a44)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(6, 9) :: tensor
    real(kind=rdp), intent(in) :: a11, a12, a44

    tensor(1, 1) = a11; tensor(1, 2) = 0.d0; tensor(1, 3) = 0.d0; tensor(1, 4) = 0.d0; tensor(1, 5) = a12; tensor(1, 6) = 0.d0; tensor(1, 7) = 0.d0; tensor(1, 8) = 0.d0; tensor(1, 9) = a12; 
    tensor(2, 1) = a12; tensor(2, 2) = 0.d0; tensor(2, 3) = 0.d0; tensor(2, 4) = 0.d0; tensor(2, 5) = a11; tensor(2, 6) = 0.d0; tensor(2, 7) = 0.d0; tensor(2, 8) = 0.d0; tensor(2, 9) = a12; 
    tensor(3, 1) = a12; tensor(3, 2) = 0.d0; tensor(3, 3) = 0.d0; tensor(3, 4) = 0.d0; tensor(3, 5) = a12; tensor(3, 6) = 0.d0; tensor(3, 7) = 0.d0; tensor(3, 8) = 0.d0; tensor(3, 9) = a11; 
    tensor(4, 1) = 0.d0; tensor(4, 2) = 0.d0; tensor(4, 3) = 0.d0; tensor(4, 4) = 0.d0; tensor(4, 5) = 0.d0; tensor(4, 6) = a44; tensor(4, 7) = 0.d0; tensor(4, 8) = a44; tensor(4, 9) = 0.d0
    tensor(5, 1) = 0.d0; tensor(5, 2) = 0.d0; tensor(5, 3) = a44; tensor(5, 4) = 0.d0; tensor(5, 5) = 0.d0; tensor(5, 6) = 0.d0; tensor(5, 7) = a44; tensor(5, 8) = 0.d0; tensor(5, 9) = 0.d0
    tensor(6, 1) = 0.d0; tensor(6, 2) = a44; tensor(6, 3) = 0.d0; tensor(6, 4) = a44; tensor(6, 5) = 0.d0; tensor(6, 6) = 0.d0; tensor(6, 7) = 0.d0; tensor(6, 8) = 0.d0; tensor(6, 9) = 0.d0

end subroutine

subroutine assignCubic2ndRankTensor(tensor, a11)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(3, 3) :: tensor
    real(kind=rdp), intent(in) :: a11

    tensor(1, 1) = a11; tensor(1, 2) = 0.d0; tensor(1, 3) = 0.d0
    tensor(2, 1) = 0.d0; tensor(2, 2) = a11; tensor(2, 3) = 0.d0
    tensor(3, 1) = 0.d0; tensor(3, 2) = 0.d0; tensor(3, 3) = a11

end subroutine

subroutine assign2ndRankTensor(tensor, a11, a22, a33)
    use nmathbasic_constants
    implicit none
    real(kind=rdp), intent(out), dimension(3, 3) :: tensor
    real(kind=rdp), intent(in) :: a11, a22, a33

    tensor(1, 1) = a11; tensor(1, 2) = 0.d0; tensor(1, 3) = 0.d0
    tensor(2, 1) = 0.d0; tensor(2, 2) = a22; tensor(2, 3) = 0.d0
    tensor(3, 1) = 0.d0; tensor(3, 2) = 0.d0; tensor(3, 3) = a33

end subroutine

