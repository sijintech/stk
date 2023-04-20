# -*- coding: utf-8 -*-
"""
Created on Sun Apr 26 10:40:37 2015

@author: cxx
"""

import numpy
from mayavi import mlab

source = mlab.pipeline.open('fei.vtk')
surf = mlab.pipeline.contour_surface(source,contours=6)

mlab.show()

#import numpy
#from mayavi.mlab import *
#
#def test_contour_surf():
#    """Test contour_surf on regularly spaced co-ordinates like MayaVi."""
#    def f(x, y):
#        sin, cos = numpy.sin, numpy.cos
#        return sin(x + y) + sin(2 * x - y) + cos(3 * x + 4 * y)
#
#    x, y = numpy.mgrid[-7.:7.05:0.1, -5.:5.05:0.05]
#    s = contour_surf(x, y, f)
#    return s
#    
#test_contour_surf()