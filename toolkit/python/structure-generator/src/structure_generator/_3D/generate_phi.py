import numpy as np
from ..basic.distribution_generator import generate_first_circle, generate_random_circle, check_overlap


def iniconf(x0, y0, z0, r0, nx, ny, nz):
    """
  Initialize the phase field variable phi for a given circle.
  """
    phi = np.zeros((nx, ny, nz))
    rr = np.zeros((nx, ny, nz))

    for ii in range(nx):
        for jj in range(ny):
            for kk in range(nz):
                rr[ii, jj, kk] = np.sqrt((ii - x0) ** 2 + (jj - y0) ** 2 + (kk - z0) ** 2)
                phi[ii, jj, kk] = 1.0 - (0.5 * np.tanh(4.0 * (rr[ii, jj, kk] - r0)) + 0.5)

    return phi


def generate_phi(nx, ny, nz, rr, shell_thickness, ptclnum, iseed):
    """
  Generate the phase field phi for multiple circles in 3D.
  """
    coordinates = []  # List to store center coordinates and radii for each circle
    phi_total = np.zeros((nx, ny, nz))  # Initialize total phi array
    phicp = np.zeros((ptclnum, nx, ny, nz))
    phics = np.zeros((ptclnum, nx, ny, nz))
    phicm = np.zeros((ptclnum, nx, ny, nz))

    # Generate the first circle at the grid center
    x_temp, y_temp, z_temp, R1, R2 = generate_first_circle(nx, ny, nz, rr, shell_thickness)
    coordinates.append((x_temp, y_temp, z_temp, R1, R2))

    # Calculate phi for the first circle
    phi1 = iniconf(x_temp, y_temp, z_temp, R1, nx, ny, nz)
    phi2 = iniconf(x_temp, y_temp, z_temp, R2, nx, ny, nz)

    phip = phi1
    phim = 1.0 - phi2
    phis = phi2 - phi1

    phicm[0] = phim
    phics[0] = phis
    phicp[0] = phip

    # Generate and calculate phi for the remaining circles
    for ic in range(2, ptclnum + 1):
        while True:
            x_temp, y_temp, z_temp, R1, R2, iseed = generate_random_circle(nx, ny, nz, rr, shell_thickness, ic, iseed)
            if not check_overlap(coordinates, x_temp, y_temp, z_temp, rr, shell_thickness):
                coordinates.append((x_temp, y_temp, z_temp, R1, R2))
                break

        # Calculate phi for the current circle
        phi1 = iniconf(x_temp, y_temp, z_temp, R1, nx, ny, nz)
        phi2 = iniconf(x_temp, y_temp, z_temp, R2, nx, ny, nz)

        phip = phi1
        phim = 1.0 - phi2
        phis = phi2 - phi1

        phicm[ic - 1] = phim
        phics[ic - 1] = phis
        phicp[ic - 1] = phip

    # Global update: Initialize phi, phip, phim, phis, phiv to zero
    phi = np.zeros((nx, ny, nz))
    phip = np.zeros((nx, ny, nz))
    phim = np.zeros((nx, ny, nz))
    phis = np.zeros((nx, ny, nz))
    phiv = np.zeros((nx, ny, nz))

    # Update the global phase field
    for nn in range(ptclnum):
        if nn % 200 == 0:  # void phase
            phiv += phicp[nn]
        else:
            phip += phicp[nn]
            phis += phics[nn]

    # Ensure the sum of phase fields equals 1
    phim = 1.0 - phip - phis - phiv

    return phim, phip, phis, phiv
