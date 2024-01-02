# -*- coding: utf-8 -*-
"""
Created on Tue Mar 10 16:16:58 2015

@author: cxx
"""

from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


filename="displace.00001001.dat_cut_1500_unload.dat"

data=pd.read_csv(filename,sep='\s*',header=None,skiprows=1)
#%%
fig = plt.figure()
ax = fig.gca(projection='3d')
X = np.arange(1, 65, 1)
Y = np.arange(1, 65, 1)
X, Y = np.meshgrid(X, Y)

#%%
Z = data.iloc[:,5].values.reshape(64,64)
surf = ax.plot_surface(X, Y, Z, rstride=1, cstride=1, cmap=cm.coolwarm,
        linewidth=0, antialiased=False)
ax.set_zlim(-1.01, 1.01)

#ax.zaxis.set_major_locator(LinearLocator(10))
#ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))
ax.view_init(10,45)
#fig.colorbar(surf, shrink=0.5, aspect=5)
plt.axis('off')
#plt.show()
plt.savefig("disp_1500_unload.png",dpi=500)