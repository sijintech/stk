Name "suan"
; 定义安装包的名称和版本
Outfile "../app_dist/suan.exe"
VIProductVersion "1.0.0"

; 定义安装程序的标题和图标
Caption "Your Installer"
Icon ".\icons\icon.ico"

; 定义安装过程中的页面和操作
Page Directory
Page InstFiles

Section
SetOutPath $INSTDIR

; 将生成的 EXE 文件添加到安装包中
File ".\dist\main\main.exe"

; 添加其他文件到安装包
File /r ".\dist\main\_internal"

SectionEnd