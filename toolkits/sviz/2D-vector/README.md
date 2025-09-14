# 3D Polarization Data Processing

This Python script processes 3D polarization data from the `Polar.00050000.dat` file, allowing you to slice specific planes, remove normal components from polarization vectors, and export to VTK format with visualization.

## Features

- **Efficient Data Reading**: Reads large 3D datasets without loading everything into memory at once
- **Plane Slicing**: Extract data from specific planes (xy, xz, yz)
- **Vector Processing**: Remove normal components from polarization vectors, keeping only in-plane components
- **VTK Export**: Export processed data to VTK format for use in ParaView or other visualization tools
- **Interactive Visualization**: Built-in VTK glyph vector visualization for quick inspection

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python polarization_process.py
```

This will:
- Read `Polar.00050000.dat`
- Slice the xy plane at z=50
- Use local polarization vectors
- Export to `polarization_output.vtk`
- Show interactive visualization

### Command Line Options

```bash
python polarization_process.py [OPTIONS]
```

**Options:**
- `--input, -i`: Input data file (default: `Polar.00050000.dat`)
- `--output, -o`: Output VTK file (default: `polarization_output.vtk`)
- `--plane, -p`: Plane to slice - `xy`, `xz`, or `yz` (default: `xy`)
- `--value, -v`: Plane coordinate value (default: `50.0`)
- `--use-global`: Use global polarization instead of local
- `--no-visualization`: Skip the interactive visualization

### Examples

1. **Slice xz plane at y=25 using global polarization:**
   ```bash
   python polarization_process.py --plane xz --value 25 --use-global
   ```

2. **Slice yz plane at x=75, no visualization:**
   ```bash
   python polarization_process.py --plane yz --value 75 --no-visualization
   ```

3. **Custom input/output files:**
   ```bash
   python polarization_process.py -i my_data.dat -o my_output.vtk
   ```

## Data Format

The input file should have:
- **Line 1**: Three integers representing dimensions (nx ny nz)
- **Subsequent lines**: Nine floating-point numbers per line:
  - Columns 1-3: x, y, z coordinates
  - Columns 4-6: Global polarization vector (px, py, pz)
  - Columns 7-9: Local polarization vector (px, py, pz)

## Output

The script generates:
1. **VTK File**: Contains the sliced plane data with in-plane polarization vectors
2. **Interactive Visualization**: 3D glyph representation of the polarization vectors

### VTK File Contents
- **Points**: Coordinates of data points on the sliced plane
- **Vectors**: In-plane polarization vectors
- **Scalars**: Magnitude of polarization vectors

## Visualization Controls

When the interactive visualization opens:
- **Left click + drag**: Rotate the view
- **Right click + drag**: Zoom in/out
- **Middle click + drag**: Pan the view
- **Press 'q'**: Quit the visualization

## Technical Details

### Plane Slicing
The script slices the 3D data along one of the three coordinate planes:
- **xy plane**: Constant z value
- **xz plane**: Constant y value  
- **yz plane**: Constant x value

### Normal Component Removal
For each polarization vector, the component normal to the plane is calculated and subtracted, leaving only the in-plane components. This is useful for analyzing 2D polarization patterns within the sliced plane.

### Memory Efficiency
The script uses NumPy's efficient array operations and VTK's streaming capabilities to handle large datasets without excessive memory usage.

## Troubleshooting

1. **File not found**: Ensure the input file path is correct
2. **Memory issues**: For very large files, consider processing smaller sections
3. **Visualization not working**: Make sure VTK is properly installed and your system supports OpenGL
4. **No data on plane**: Try different plane values or check the coordinate ranges in your data

## Dependencies

- **NumPy**: Numerical computations and array operations
- **VTK**: Visualization and VTK file format support
