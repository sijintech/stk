# STK - Suan Toolkit

- suan: for the unified CLI and GUI platform to support scientific computing
- toolkit: for the plugins to be used on the suan platform

In the future, we have the toolkit folder as the backend with many unit tests, and the suan folder as the frontend with GUI and CLI with many integrated tests.

For now the toolkit folder contains cpp subfolders because they are far from ready as a plugin, in the future each subfolder of the toolkit folder should be a plugin which may contain both cpp or python or any language's codes.



## File format

- C/C++: clang-format
- fortran: fprettify
- python: black
- shell: shfmt
- js: prettier