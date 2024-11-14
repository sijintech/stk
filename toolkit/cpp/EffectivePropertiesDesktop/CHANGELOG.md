# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changelog rules:
- **Added** for new features.
- **Changed** for changes in existing functionality.
- **Deprecated** for soon-to-be removed features.
- **Removed** for now removed features.
- **Fixed** for any bug fixes.
- **Security** in case of vulnerabilities.

Semantic versioning rules:
- **MAJOR** version when you make incompatible API changes,
- **MINOR** version when you add functionality in a backwards compatible manner, and
- **PATCH** version when you make backwards compatible bug fixes.

## [Unreleased]

## [0.2.2] - 2022-04-19
1. Fix the bug unsupported protocols when license verification
2. Fix the bug missing mkl_def.2.dll

## [0.2.1] - 2022-03-24
1. Update license, use device id instead of product id

## [0.2.0] - 2022-02-04
1. Update UI
2. Fix some bug in the main, that the input file format is incompatible with GUI

## [0.1.9] - 2021-11-17
### Changed
1. Switch to intel oneapi compiler

## [0.1.8] - 2021-10-19
### Fixed
1. Some bugs in the export of input.xml 
2. Some incorrect render in documetation

## [0.1.7] - 2021-10-15
### Fixed
1. The import of phase and tensor part.
### Changed
1. Update documentation from markdown to doxygen.

## [0.1.6] - 2021-09-30
### Changed
1. Now using gui component from npmjs
2. Update core input 

## [0.1.5] - 2021-09-16
### Changed
1. Update the tensor input style. Now the possibility of repeating index is elmininated.
2. Remove the plus sign for the geometry input, user should always use the "Add geometry" button to add new geometry.
3. A notification message will be shown if the input.xml file is successfully created.

## [0.1.4] - 2021-09-10
### Changed
1. Migrate to coding.net
2. Fully migrate from meson to cmake
3. set up the CI/CD for jenkins on coding.net

## [0.1.3] - 2021-08-25
### Fixed
- The "Distribution" switch is not updating when import from file, need to add the option *valuePropName="checked"* to form item.
### Changed
- Update the input example at [here](https://mupro-effprop.surge.sh/documentations/input/input/). Now it works with import.
