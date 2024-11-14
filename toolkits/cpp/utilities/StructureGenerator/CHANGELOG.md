# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

[Unreleased]

## [0.1.4] - 2021-10-07

### Added

1. Using doxygen + doxybook2 to create the pdf and markdown version of the user manual.

## [0.1.3] - 2021-09-30

### Fixed

1. Fix a bug, when reading from multiple tensor of a phase, the rank is always determined by the first one. Now add a function n_material_get_tensor_rank to get the rank of a tensor.

## [0.1.2] - 2021-09-17

### Changed

1. Add the fortran interface for n_material_generator_rank0.

## [0.1.1] - 2021-09-16

### Changed

1. Change the name of structure assign 3D data interface for fortran, now it is called n_structure_assign_data_rank0, which is more consistent with other similar subroutines
