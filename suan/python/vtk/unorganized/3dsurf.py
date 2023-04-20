# -*- coding: utf-8 -*-
"""
Created on Mon Feb  2 16:12:36 2015

plotting 3D with any function
@author: cxx
"""

from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import numpy as np
import matplotlib.pyplot as plt

fig = plt.figure()
ax = fig.gca(projection='3d')
x = np.arange(-0.1,0.1,0.0025)
y = np.arange(-0.1,0.1,0.0025)
x, y = np.meshgrid(x,y)
z = x*(x**2-y**2)/((x**2+y**2)**2)

surf = ax.plot_surface(x, y, z, rstride=1, cstride=1, cmap=cm.coolwarm,
        linewidth=0, antialiased=True)

ax.zaxis.set_major_locator(LinearLocator(10))
ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))

fig.colorbar(surf, shrink=0.5, aspect=5)
plt.show()

#from mpl_toolkits.mplot3d import Axes3D
#from matplotlib import cm
#from matplotlib.ticker import LinearLocator, FormatStrFormatter
#import matplotlib.pyplot as plt
#import numpy as np
#
#fig = plt.figure()
#ax = fig.gca(projection='3d')
#X = np.arange(-5, 5, 0.25)
#Y = np.arange(-5, 5, 0.25)
#X, Y = np.meshgrid(X, Y)
#R = np.sqrt(X**2 + Y**2)
#Z = np.sin(R)
#surf = ax.plot_surface(X, Y, Z, rstride=1, cstride=1, cmap=cm.coolwarm,
#        linewidth=0, antialiased=False)
#ax.set_zlim(-1.01, 1.01)
#
#ax.zaxis.set_major_locator(LinearLocator(10))
#ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))
#
#fig.colorbar(surf, shrink=0.5, aspect=5)
#
#plt.show()