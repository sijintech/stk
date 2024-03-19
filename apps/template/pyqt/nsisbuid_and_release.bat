@echo off

REM 检查输入参数，确保至少有一个参数（tag）
IF "%1"=="" (
    echo Usage: %0 TAG
    exit /b 1
)
REM Setup virtual environment
python -m venv .venv
call .venv\Scripts\activate 

REM Upgrade pip
REM pip install -U pip
python.exe -m pip install -U pip

REM 设置需要检查的python软件包列表
set "PACKAGES=pyinstaller PySide6 vtk matplotlib pandas numpy"

REM 创建临时文件来存储 `pip show` 命令的输出
set "TEMP_FILE=%TEMP%\pip_show_output.txt"

REM 遍历软件包列表并检查是否已安装
for %%i in (%PACKAGES%) do (
    pip show %%i > "%TEMP_FILE%"
    findstr /C:"Name: %%i" "%TEMP_FILE%" > nul
    if errorlevel 1 (
        echo %%i is not installed.
        REM 在这里执行安装命令，例如：pip install %%i
        pip install %%i
    ) else (
        echo %%i is already installed.
    )
)

REM 删除临时文件
del "%TEMP_FILE%"

REM 本地打包exe
cd .\src
pyinstaller .\main.spec
cd ..\


REM 执行 git 操作
REM git lfs track .\src\dist\suan_pyqt.zip
git add .
git commit -m "Release %1"
git tag v%1 
git push --tag