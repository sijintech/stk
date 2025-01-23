# STK - Suan Toolkit

stk就是一个python的工具包，为模拟计算（当前主要针对MuPRO软件的使用场景）提供一些前后处理的支持。
使用pip安装stk后，支持三种使用方式，命令行使用（suan），图形界面使用（suan-gui），编程使用（import suan）。

文件夹结构：

- suan：提供用户使用的界面，有cli，gui
- toolkits：提供具体功能的一些函数，有数据、可视化等，其中每个子文件夹是一个subpackage。


## File format

- C/C++: clang-format
- fortran: fprettify
- python: black
- shell: shfmt
- js: prettier
