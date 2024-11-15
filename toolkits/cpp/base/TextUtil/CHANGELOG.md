# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

[Unreleased]

1. Switch to fully cmake workflow
2. Add integration with ctest
3. Add examples for using the lib in different languages

## [0.1.2] - 2021-09-16

### Fixed

1. Add the f90 to CMakeLists.txt in the library, otherwise there won't be the ntextutils.mod needed by programs such as dielectric-breakdown

## [0.1.1] - 2021-09-09

### Fixed

1. line 423 ntextutils.c, move the buffer free into the same scope as it is allocated

## [0.1.0] - 2021-08-28

### Added

1. Migrate to coding.net
