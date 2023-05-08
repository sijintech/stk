---
title: Convert MUPRO data to vtk format
lang: en-US
---
# python-vtk
Create a **Data** class that convert between *.dat* data file, numpy array, and *.vtk* file

# Prerequisite
1. **python**, if you have never used python before, I recomment trying the *Anaconda Distribution*  [https://www.anaconda.com/distribution/](https://www.anaconda.com/distribution/)
2. **paraview**, [https://www.paraview.org/download/](https://www.paraview.org/download/)

# Folder and Files
- **test** contains testing data *PELOOP.00001000.dat* and example vtk legacy file *example.vtk*
- **nt_vtk.py** the module file, that you need to put into your data processing directory and import

# Usage
``` python
import nt_vtk

#Initial a Data object, first arguement is the data file name,
# second arguement is the data type
data = nt_vtk.Data("PELOOP.00001000.dat",nt_vtk.SCALAR)   # Read the data as a scalar
# data = nt_vtk.Data("PELOOP.00001000.dat",nt_vtk.VECTOR) # Read the data as a vector
# data = nt_vtk.Data("PELOOP.00001000.dat",nt_vtk.DOMAIN) # Read the data as domain data

np_array = data.get_np_array()  # Return the data as a numpy array, you can put it into your usual data processing process
data.get_vtk_file('test_scalar.vtk') # Output the vtk file
```

# Visualization
## Scalar
![](/Scalar.png)

## Vector
![](/Vector.png)

## Domain
![](/Domain.png)
