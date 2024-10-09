# data
## Instruction
Function planning in the Python library:
```python
data
    - data_handling
    - drawing
    - plotting
    - research
    - scripts
    - statistics
    - utils
```

##  How to use
### install
You can build the package by running the following commands in the directory where the `pyproject.toml` is located, depending on the operating system. The built package will appear in the dist folder
```bash
pip install build
# Windows
py -m build
# Unix/macOS
python3 -m build
```
After, you can install the package under `dist` folder by running command
```bash
pip install ./data-0.0.1-py3-none-any.whl
```
We publish the package on PyPI website, you can install the package by running command
```bash
pip install stk-date
```
### import package in python
```python
# import package
import stk_data
from stk_data.statistics import get_skyrmion_shape
nx = 250
ny = 250
nz = 10
nk = 6
nR = 100
dx = 2.0
dy = 2.0
load_file_name = 'path/to/load_file'
save_file_name = 'path/to/save_file'

get_skyrmion_shape(nx, ny, nz, nk, nR, dx, dy, load_file_name, save_file_name)

```
### scripts
1. Calculate the topological number, parameters can be read and calculated via commands, terminal command as follows:
```bash
# usage: get_skyrmion_shape [-h] [--nx NX] [--ny NY] [--nz NZ] [--nk NK] [--nR NR] [--dx DX] [--dy DY] [--load_file_name LOAD_FILE_NAME] [--save_file_name SAVE_FILE_NAME]

# use examples
get_skyrmion_shape --nx 250 --ny 250 --nz 10 --nk 6 --nR 100 --dx 2.0 --dy 2.0 --load_file_name magnt.in --save_file_name GetSkyrmionShape120.dat

```
