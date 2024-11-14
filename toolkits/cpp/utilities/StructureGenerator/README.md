#structure-generator
migration from gitee nstructure-generator b8d7c720870160d68a26a9250bd60f9ce76f80ca 2021 Aug 27 23:47:57

CC=gcc-10 meson builddir
export LIBRARY_PATH=/Library/Developer/CommandLineTools/SDKs/MacOSX11.1.sdk/usr/lib/:/usr/local/Cellar/gcc/10.2.0/lib/gcc/10

When rank = 0, won't read symmetry and index, value is directly set from the value.
When rank = 1, 2, won't read the symmetry, all treated as a custom symmetry.
When rank higher than 2, you can use symmetry to help with input (we only have 4th rank tensor rules now).
Add the fortran module for n_material_generator, and n_material_generator_one_phase
Add tensor print whenever it is read from the xml file
Change some function names in fortran module:

- n_material_generator_rank2
- n_material_generator_rank1
- n_material_generator_one_phase_rank2
- n_structure_assign_data_rank2
- n_structure_assign_data_rank1

source /opt/intel/oneapi/setvars.sh
CC=icc CXX=icpc FC=ifort cmake -DCMAKE_VERBOSE_MAKEFILE=TRUE ..
