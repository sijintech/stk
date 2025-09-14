#!/usr/bin/env python3
"""
3D Polarization Data Processing Script

This script processes 3D polarization data from Polar.00050000.dat file:
1. Reads the 3D dataset with dimensions and coordinate/polarization data
2. Slices a specific plane from the 3D data
3. Removes normal component from polarization vectors (keeps in-plane components)
4. Exports data to VTK format
5. Creates VTK glyph vector visualization for inspection

Data format:
- Line 1: nx ny nz (dimensions)
- Each line: x y z global_px global_py global_pz local_px local_py local_pz
"""

import numpy as np
import vtk
from vtk.util import numpy_support
import argparse
import os
import sys
from typing import Tuple, Optional
from tqdm import tqdm


class PolarizationProcessor:
    """
    Class to handle 3D polarization data processing and visualization
    """
    
    def __init__(self, data_file: str):
        """
        Initialize the processor with data file path
        
        Args:
            data_file: Path to the polarization data file
        """
        self.data_file = data_file
        self.dimensions = None
        self.coordinates = None
        self.global_polarization = None
        self.local_polarization = None
        self.plane_data = None
        
    def read_data(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Read the 3D polarization data from file
        
        Returns:
            Tuple of (coordinates, global_polarization, local_polarization, dimensions)
        """
        print(f"Reading data from {self.data_file}...")
        
        # Read first line to get dimensions
        with open(self.data_file, 'r') as f:
            first_line = f.readline().strip()
            self.dimensions = np.array([int(x) for x in first_line.split()])
            print(f"Data dimensions: {self.dimensions}")
            
        # Read the rest of the data with progress bar
        print("Loading data points...")
        data = np.loadtxt(self.data_file, skiprows=1)
        
        # Extract coordinates and polarization vectors
        self.coordinates = data[:, :3]  # x, y, z coordinates
        self.global_polarization = data[:, 3:6]  # global polarization vector
        self.local_polarization = data[:, 6:9]  # local polarization vector
        
        print(f"Loaded {len(data)} data points")
        print(f"Coordinate range: X[{self.coordinates[:, 0].min():.2f}, {self.coordinates[:, 0].max():.2f}], "
              f"Y[{self.coordinates[:, 1].min():.2f}, {self.coordinates[:, 1].max():.2f}], "
              f"Z[{self.coordinates[:, 2].min():.2f}, {self.coordinates[:, 2].max():.2f}]")
        
        return self.coordinates, self.global_polarization, self.local_polarization, self.dimensions
    
    def slice_plane(self, plane_type: str = 'xy', plane_value: float = 50.0, 
                   use_global: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Slice a plane from the 3D data
        
        Args:
            plane_type: Type of plane ('xy', 'xz', 'yz')
            plane_value: Value of the plane coordinate
            use_global: If True, use global polarization; if False, use local polarization
            
        Returns:
            Tuple of (plane_coordinates, plane_polarization, plane_indices)
        """
        # Determine which coordinate to slice
        if plane_type == 'xy':
            coord_idx = 2  # slice along z
            coord_name = 'z'
        elif plane_type == 'xz':
            coord_idx = 1  # slice along y
            coord_name = 'y'
        elif plane_type == 'yz':
            coord_idx = 0  # slice along x
            coord_name = 'x'
        
        print(f"Slicing {plane_type} plane at {coord_name} = {plane_value}")
        
        if plane_type not in ['xy', 'xz', 'yz']:
            raise ValueError("plane_type must be 'xy', 'xz', or 'yz'")
        
        # Find points on the plane (with some tolerance for floating point)
        tolerance = 0.5
        plane_mask = np.abs(self.coordinates[:, coord_idx] - plane_value) < tolerance
        
        # Extract plane data
        plane_coords = self.coordinates[plane_mask]
        if use_global:
            plane_polarization = self.global_polarization[plane_mask]
        else:
            plane_polarization = self.local_polarization[plane_mask]
        
        plane_indices = np.where(plane_mask)[0]
        
        print(f"Found {len(plane_coords)} points on {plane_type} plane")
        
        self.plane_data = {
            'coordinates': plane_coords,
            'polarization': plane_polarization,
            'indices': plane_indices,
            'plane_type': plane_type,
            'plane_value': plane_value
        }
        
        return plane_coords, plane_polarization, plane_indices
    
    def remove_normal_component(self, plane_coords: np.ndarray, 
                              plane_polarization: np.ndarray) -> np.ndarray:
        """
        Remove the normal component from polarization vectors, keeping only in-plane components
        
        Args:
            plane_coords: Coordinates of points on the plane
            plane_polarization: Polarization vectors at those points
            
        Returns:
            In-plane polarization vectors
        """
        print("Removing normal component from polarization vectors...")
        
        # Get plane normal vector
        plane_type = self.plane_data['plane_type']
        if plane_type == 'xy':
            normal = np.array([0, 0, 1])  # z-direction
        elif plane_type == 'xz':
            normal = np.array([0, 1, 0])  # y-direction
        elif plane_type == 'yz':
            normal = np.array([1, 0, 0])  # x-direction
        
        # Calculate normal component for each vector
        normal_components = np.dot(plane_polarization, normal)
        
        # Remove normal component
        in_plane_polarization = plane_polarization - np.outer(normal_components, normal)
        
        print(f"Original polarization magnitude range: [{np.linalg.norm(plane_polarization, axis=1).min():.4f}, "
              f"{np.linalg.norm(plane_polarization, axis=1).max():.4f}]")
        print(f"In-plane polarization magnitude range: [{np.linalg.norm(in_plane_polarization, axis=1).min():.4f}, "
              f"{np.linalg.norm(in_plane_polarization, axis=1).max():.4f}]")
        
        return in_plane_polarization
    
    def export_to_vtk(self, output_file: str, plane_coords: np.ndarray, 
                     in_plane_polarization: np.ndarray) -> None:
        """
        Export the processed data to VTK structured grid format
        
        Args:
            output_file: Output VTK file path
            plane_coords: Coordinates of points on the plane
            in_plane_polarization: In-plane polarization vectors
        """
        print(f"Exporting data to VTK structured grid format: {output_file}")
        
        # Determine grid dimensions based on plane type
        plane_type = self.plane_data['plane_type']
        
        if plane_type == 'xy':
            # Grid in x-y plane, constant z
            x_coords = np.unique(plane_coords[:, 0])
            y_coords = np.unique(plane_coords[:, 1])
            z_coords = np.unique(plane_coords[:, 2])
            dims = [len(x_coords), len(y_coords), 1]
        elif plane_type == 'xz':
            # Grid in x-z plane, constant y
            x_coords = np.unique(plane_coords[:, 0])
            y_coords = np.unique(plane_coords[:, 1])
            z_coords = np.unique(plane_coords[:, 2])
            dims = [len(x_coords), 1, len(z_coords)]
        elif plane_type == 'yz':
            # Grid in y-z plane, constant x
            x_coords = np.unique(plane_coords[:, 0])
            y_coords = np.unique(plane_coords[:, 1])
            z_coords = np.unique(plane_coords[:, 2])
            dims = [1, len(y_coords), len(z_coords)]
        
        print(f"Structured grid dimensions: {dims}")
        
        # Create structured grid
        sgrid = vtk.vtkStructuredGrid()
        sgrid.SetDimensions(dims)
        
        # Create points for structured grid
        vtk_points = vtk.vtkPoints()
        
        # Sort coordinates to match VTK structured grid ordering
        print("Creating structured grid points...")
        total_points = dims[0] * dims[1] * dims[2]
        
        if plane_type == 'xy':
            with tqdm(total=total_points, desc="Processing xy plane points") as pbar:
                for y in y_coords:
                    for x in x_coords:
                        # Find the point with these x,y coordinates
                        mask = (np.abs(plane_coords[:, 0] - x) < 1e-6) & (np.abs(plane_coords[:, 1] - y) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            vtk_points.InsertNextPoint(plane_coords[idx])
                        else:
                            vtk_points.InsertNextPoint(x, y, z_coords[0])
                        pbar.update(1)
        elif plane_type == 'xz':
            with tqdm(total=total_points, desc="Processing xz plane points") as pbar:
                for z in z_coords:
                    for x in x_coords:
                        # Find the point with these x,z coordinates
                        mask = (np.abs(plane_coords[:, 0] - x) < 1e-6) & (np.abs(plane_coords[:, 2] - z) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            vtk_points.InsertNextPoint(plane_coords[idx])
                        else:
                            vtk_points.InsertNextPoint(x, y_coords[0], z)
                        pbar.update(1)
        elif plane_type == 'yz':
            with tqdm(total=total_points, desc="Processing yz plane points") as pbar:
                for z in z_coords:
                    for y in y_coords:
                        # Find the point with these y,z coordinates
                        mask = (np.abs(plane_coords[:, 1] - y) < 1e-6) & (np.abs(plane_coords[:, 2] - z) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            vtk_points.InsertNextPoint(plane_coords[idx])
                        else:
                            vtk_points.InsertNextPoint(x_coords[0], y, z)
                        pbar.update(1)
        
        sgrid.SetPoints(vtk_points)
        
        # Create arrays for vector and scalar data in structured grid order
        structured_vectors = np.zeros((dims[0] * dims[1] * dims[2], 3))
        structured_magnitudes = np.zeros(dims[0] * dims[1] * dims[2])
        
        # Fill the structured arrays
        print("Processing vector data...")
        point_idx = 0
        if plane_type == 'xy':
            with tqdm(total=total_points, desc="Processing xy vectors") as pbar:
                for y in y_coords:
                    for x in x_coords:
                        mask = (np.abs(plane_coords[:, 0] - x) < 1e-6) & (np.abs(plane_coords[:, 1] - y) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            structured_vectors[point_idx] = in_plane_polarization[idx]
                            structured_magnitudes[point_idx] = np.linalg.norm(in_plane_polarization[idx])
                        point_idx += 1
                        pbar.update(1)
        elif plane_type == 'xz':
            with tqdm(total=total_points, desc="Processing xz vectors") as pbar:
                for z in z_coords:
                    for x in x_coords:
                        mask = (np.abs(plane_coords[:, 0] - x) < 1e-6) & (np.abs(plane_coords[:, 2] - z) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            structured_vectors[point_idx] = in_plane_polarization[idx]
                            structured_magnitudes[point_idx] = np.linalg.norm(in_plane_polarization[idx])
                        point_idx += 1
                        pbar.update(1)
        elif plane_type == 'yz':
            with tqdm(total=total_points, desc="Processing yz vectors") as pbar:
                for z in z_coords:
                    for y in y_coords:
                        mask = (np.abs(plane_coords[:, 1] - y) < 1e-6) & (np.abs(plane_coords[:, 2] - z) < 1e-6)
                        if np.any(mask):
                            idx = np.where(mask)[0][0]
                            structured_vectors[point_idx] = in_plane_polarization[idx]
                            structured_magnitudes[point_idx] = np.linalg.norm(in_plane_polarization[idx])
                        point_idx += 1
                        pbar.update(1)
        
        # Add polarization vectors as point data
        vtk_vectors = numpy_support.numpy_to_vtk(structured_vectors, deep=True)
        vtk_vectors.SetName("InPlanePolarization")
        sgrid.GetPointData().SetVectors(vtk_vectors)
        
        # Add magnitude as scalar data
        vtk_magnitudes = numpy_support.numpy_to_vtk(structured_magnitudes, deep=True)
        vtk_magnitudes.SetName("PolarizationMagnitude")
        sgrid.GetPointData().SetScalars(vtk_magnitudes)
        
        # Write to file
        print("Writing VTK file...")
        writer = vtk.vtkStructuredGridWriter()
        writer.SetFileName(output_file)
        writer.SetInputData(sgrid)
        writer.Write()
        
        print(f"VTK structured grid file saved: {output_file}")
    
    def create_visualization(self, plane_coords: np.ndarray, 
                           in_plane_polarization: np.ndarray) -> None:
        """
        Create VTK glyph vector visualization for quick inspection
        
        Args:
            plane_coords: Coordinates of points on the plane
            in_plane_polarization: In-plane polarization vectors
        """
        print("Creating VTK visualization...")
        
        # Create VTK points
        vtk_points = vtk.vtkPoints()
        for coord in plane_coords:
            vtk_points.InsertNextPoint(coord)
        
        # Create polydata
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(vtk_points)
        
        # Add polarization vectors
        vtk_vectors = numpy_support.numpy_to_vtk(in_plane_polarization, deep=True)
        vtk_vectors.SetName("PolarizationVectors")
        polydata.GetPointData().SetVectors(vtk_vectors)
        
        # Add magnitude as scalars
        magnitudes = np.linalg.norm(in_plane_polarization, axis=1)
        vtk_magnitudes = numpy_support.numpy_to_vtk(magnitudes, deep=True)
        vtk_magnitudes.SetName("Magnitude")
        polydata.GetPointData().SetScalars(vtk_magnitudes)
        
        # Create arrow source for glyphs
        arrow_source = vtk.vtkArrowSource()
        arrow_source.SetTipResolution(6)
        arrow_source.SetShaftResolution(6)
        
        # Calculate adaptive scale factor to make largest vector scale to 1
        max_magnitude = np.max(magnitudes)
        adaptive_scale_factor = 1.0 / max_magnitude if max_magnitude > 0 else 1.0
        
        # Create glyph3D
        glyph = vtk.vtkGlyph3D()
        glyph.SetInputData(polydata)
        glyph.SetSourceConnection(arrow_source.GetOutputPort())
        glyph.SetVectorModeToUseVector()
        glyph.SetScaleModeToScaleByVector()
        glyph.SetScaleFactor(adaptive_scale_factor)  # Adaptive scale to make largest vector = 1
        glyph.Update()
        
        # Create mapper
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(glyph.GetOutputPort())
        mapper.SetScalarModeToUsePointData()
        mapper.SetScalarRange(magnitudes.min(), magnitudes.max())
        
        # Create actor
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        
        # Create renderer
        renderer = vtk.vtkRenderer()
        renderer.AddActor(actor)
        renderer.SetBackground(0.1, 0.1, 0.1)
        
        # Create render window
        render_window = vtk.vtkRenderWindow()
        render_window.AddRenderer(renderer)
        render_window.SetSize(800, 600)
        render_window.SetWindowName("Polarization Vector Visualization")
        
        # Create interactor
        interactor = vtk.vtkRenderWindowInteractor()
        interactor.SetRenderWindow(render_window)
        
        # Add axes
        axes = vtk.vtkAxesActor()
        axes.SetTotalLength(10, 10, 10)
        renderer.AddActor(axes)
        
        # Start interaction
        print("Starting visualization... Use mouse to interact:")
        print("- Left click and drag: rotate")
        print("- Right click and drag: zoom")
        print("- Middle click and drag: pan")
        print("- Press 'q' to quit")
        
        interactor.Initialize()
        interactor.Start()


def main():
    """
    Main function to process polarization data
    """
    parser = argparse.ArgumentParser(description='Process 3D polarization data')
    parser.add_argument('--input', '-i', default='Polar.00050000.dat',
                       help='Input data file (default: Polar.00050000.dat)')
    parser.add_argument('--output', '-o', default='polarization_output.vtk',
                       help='Output VTK file (default: polarization_output.vtk)')
    parser.add_argument('--plane', '-p', choices=['xy', 'xz', 'yz'], default='xy',
                       help='Plane to slice (default: xy)')
    parser.add_argument('--value', '-v', type=float, default=50.0,
                       help='Plane coordinate value (default: 50.0)')
    parser.add_argument('--use-global', action='store_true',
                       help='Use global polarization instead of local')
    parser.add_argument('--no-visualization', action='store_true',
                       help='Skip visualization')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found!")
        sys.exit(1)
    
    # Create processor
    processor = PolarizationProcessor(args.input)
    
    try:
        # Read data
        coordinates, global_pol, local_pol, dimensions = processor.read_data()
        
        # Slice plane
        plane_coords, plane_polarization, plane_indices = processor.slice_plane(
            plane_type=args.plane,
            plane_value=args.value,
            use_global=args.use_global
        )
        
        # Remove normal component
        in_plane_polarization = processor.remove_normal_component(
            plane_coords, plane_polarization
        )
        
        # Export to VTK
        processor.export_to_vtk(args.output, plane_coords, in_plane_polarization)
        
        # Create visualization
        if not args.no_visualization:
            processor.create_visualization(plane_coords, in_plane_polarization)
        
        print("Processing completed successfully!")
        
    except Exception as e:
        print(f"Error during processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
