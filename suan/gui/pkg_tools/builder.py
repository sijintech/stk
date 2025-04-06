#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
STK自动打包脚本 - 优化PyInstaller打包流程
"""

import os
import sys
import argparse
import subprocess
import platform
import logging
import shutil
import tempfile
import time
from pathlib import Path
from datetime import datetime

# 导入本地模块
from .hooks_generator import generate_all_hooks, ensure_hooks_dir


def setup_logging(log_dir=None, debug=False):
    """设置日志"""
    if log_dir is None:
        script_dir = Path(__file__).parent.parent
        log_dir = script_dir / "build_logs"
    
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"build_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    log_level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)  # 明确指定输出到标准输出
        ]
    )
    return logging.getLogger("stk_build")


def is_venv_active():
    """检查是否在虚拟环境中"""
    return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)


def activate_venv():
    """激活虚拟环境"""
    logger = logging.getLogger("stk_build")
    if is_venv_active():
        logger.info("已在虚拟环境中运行")
        return True
    
    logger.warning("未在虚拟环境中运行，尝试激活虚拟环境")
    
    # 尝试找到项目根目录的.venv目录
    script_dir = Path(__file__).parent.parent.parent
    project_root = script_dir.parent
    
    # 检查常见的虚拟环境位置
    venv_paths = [
        project_root / ".venv",
        project_root / "venv",
        project_root / "env",
    ]
    
    for venv_path in venv_paths:
        if not venv_path.exists():
            continue
        
        # 根据平台选择激活脚本
        if platform.system() == "Windows":
            activate_script = venv_path / "Scripts" / "activate.bat"
            if activate_script.exists():
                logger.info(f"找到虚拟环境: {venv_path}")
                logger.info("请在激活虚拟环境后重新运行此脚本:")
                print(f"\n请运行:\n{activate_script} && python -m suan.gui.packaging.builder 参数...\n")
                return False
        else:
            activate_script = venv_path / "bin" / "activate"
            if activate_script.exists():
                logger.info(f"找到虚拟环境: {venv_path}")
                logger.info("请在激活虚拟环境后重新运行此脚本:")
                print(f"\n请运行:\nsource {activate_script} && python -m suan.gui.packaging.builder 参数...\n")
                return False
    
    logger.error("未找到虚拟环境，请确保已使用 Poetry 或其他工具创建虚拟环境")
    print("\n您可以尝试运行:\npython -m venv .venv\n")
    return False


def clean_build_dirs(logger, dry_run=False):
    """清理旧的构建目录"""
    script_dir = Path(__file__).parent.parent
    
    dirs_to_clean = [
        script_dir / "build",
        script_dir / "dist",
        script_dir / "__pycache__"
    ]
    
    for pyc_file in script_dir.glob("*.pyc"):
        if dry_run:
            logger.info(f"将删除文件(模拟): {pyc_file}")
        else:
            logger.info(f"删除文件: {pyc_file}")
            try:
                os.remove(pyc_file)
            except Exception as e:
                logger.warning(f"删除文件 {pyc_file} 失败: {e}")
    
    for dir_path in dirs_to_clean:
        if dir_path.exists():
            if dry_run:
                logger.info(f"将删除目录(模拟): {dir_path}")
            else:
                logger.info(f"删除目录: {dir_path}")
                try:
                    shutil.rmtree(dir_path)
                except Exception as e:
                    logger.warning(f"删除目录 {dir_path} 失败: {e}")


def check_dependencies(logger):
    """检查必要的依赖是否已安装"""
    # 需要检查的包和可能的导入名称映射
    required_packages = {
        "pyinstaller": ["pyinstaller", "PyInstaller"],
        "pyinstaller-hooks-contrib": ["_pyinstaller_hooks_contrib"],
        "toml": ["toml"]
    }
    
    missing_packages = []
    for package_name, import_names in required_packages.items():
        found = False
        for import_name in import_names:
            try:
                # 特殊处理pyinstaller-hooks-contrib
                if import_name == "_pyinstaller_hooks_contrib":
                    import os
                    import site
                    # 检查site-packages目录中是否存在_pyinstaller_hooks_contrib目录
                    site_packages = site.getsitepackages()
                    for site_pkg in site_packages:
                        if os.path.exists(os.path.join(site_pkg, "_pyinstaller_hooks_contrib")):
                            found = True
                            break
                else:
                    __import__(import_name)
                    found = True
                break
            except ImportError:
                continue
        
        if not found:
            missing_packages.append(package_name)
    
    if missing_packages:
        logger.error(f"缺少必要的依赖包: {', '.join(missing_packages)}")
        logger.info("请使用以下命令安装:")
        pip_cmd = "pip install " + " ".join(missing_packages)
        logger.info(f"  {pip_cmd}")
        return False
    
    logger.info("所有必要的依赖已安装")
    return True


def create_spec_file(logger, platform_specific=True):
    """创建或更新spec文件"""
    scripts_dir = Path(__file__).parent
    gui_dir = scripts_dir.parent
    
    # 确保spec文件位于gui目录，而不是packaging目录
    template_spec = gui_dir / "main.spec"
    
    if not template_spec.exists():
        logger.error(f"模板spec文件不存在: {template_spec}")
        return None
    
    if not platform_specific:
        return template_spec
    
    # 创建平台特定的spec文件
    system = platform.system()
    if system == "Windows":
        platform_spec = gui_dir / "windows.spec"
    elif system == "Darwin":
        platform_spec = gui_dir / "macos.spec"
    else:
        platform_spec = gui_dir / "linux.spec"
    
    # 复制模板spec文件内容
    shutil.copy2(template_spec, platform_spec)
    logger.info(f"已创建平台特定的spec文件: {platform_spec}")
    return platform_spec


def run_pyinstaller(logger, args):
    """运行PyInstaller打包"""
    scripts_dir = Path(__file__).parent
    gui_dir = scripts_dir.parent
    
    # 在打包前自动生成钩子文件
    try:
        logger.info("生成钩子文件...")
        if generate_all_hooks():
            logger.info("成功生成所有钩子文件")
        else:
            logger.warning("部分钩子文件生成失败，使用已有的钩子文件继续")
    except Exception as e:
        logger.warning(f"生成钩子文件失败: {e}，使用已有的钩子文件继续")
    
    # 确定要使用的spec文件
    if args.spec_file:
        spec_file = args.spec_file
    else:
        spec_file = create_spec_file(logger, args.platform_specific)
        if not spec_file:
            return False
    
    # 构建PyInstaller命令 - 注意工作目录需要是gui目录
    os.chdir(gui_dir)
    cmd = ["pyinstaller"]
    
    # 添加参数
    cmd.append(str(spec_file))
    
    if args.clean:
        clean_build_dirs(logger, dry_run=False)
    
    if args.debug:
        cmd.append("--log-level=DEBUG")  # 使用日志级别参数代替调试参数
    
    # 使用spec文件时，不应该传递以下参数，因为这些设置应该在spec文件中定义
    # 只有在未使用spec文件直接打包main.py时，才应该使用这些参数
    using_spec_file = True  # 我们总是使用spec文件
    
    if not using_spec_file:
        if args.onedir:
            cmd.append("--onedir")
        
        if args.console:
            cmd.append("--console")
    elif args.console or args.onedir:
        logger.warning("使用spec文件时，--console和--onedir选项将被忽略")
        logger.info("请直接在spec文件中修改这些设置")
    
    # 运行命令
    logger.info(f"运行命令: {' '.join(cmd)}")
    start_time = time.time()
    
    try:
        # 在Windows上，使用shell=True可能会解决一些路径问题
        use_shell = platform.system() == "Windows"
        
        # 使用实时输出方式运行命令
        logger.info("开始执行PyInstaller，输出如下:")
        print("-" * 80)
        
        # 默认不捕获输出，让所有输出直接显示在控制台
        process = subprocess.run(cmd, check=True, shell=use_shell)
        
        print("-" * 80)
        end_time = time.time()
        logger.info(f"PyInstaller打包完成，耗时 {end_time - start_time:.2f} 秒")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"PyInstaller打包失败: {e}")
        return False


def verify_build(logger, args):
    """验证打包结果"""
    scripts_dir = Path(__file__).parent
    gui_dir = scripts_dir.parent
    dist_dir = gui_dir / "dist"
    
    # 根据操作系统确定可执行文件名
    system = platform.system()
    if system == "Windows":
        exe_name = "stk_windows.exe"
    elif system == "Darwin":
        exe_name = "stk_macos"
    else:
        exe_name = "stk_ubuntu"
    
    # 如果使用了--onedir选项，可执行文件会在子目录中
    if args.onedir:
        exe_path = dist_dir / exe_name.split(".")[0] / exe_name
    else:
        exe_path = dist_dir / exe_name
    
    if not exe_path.exists():
        logger.error(f"打包验证失败: 可执行文件不存在 {exe_path}")
        return False
    
    logger.info(f"可执行文件已生成: {exe_path}")
    logger.info(f"文件大小: {exe_path.stat().st_size / (1024*1024):.2f} MB")
    
    # 验证重要文件是否存在（针对onedir模式）
    if args.onedir:
        exe_dir = exe_path.parent
        important_modules = [
            "left_sidebar.py", 
            "right_sidebar.py", 
            "toolbar.py", 
            "statusbar.py", 
            "info_bar.py", 
            "center_widget.py"
        ]
        
        for module in important_modules:
            module_path = exe_dir / module
            if not module_path.exists():
                logger.warning(f"注意: 模块文件 {module} 可能未被正确打包")
    
    if args.test_run:
        logger.info("测试运行打包后的应用...")
        try:
            # 仅运行几秒然后终止
            process = subprocess.Popen([str(exe_path)])
            logger.info("应用已启动，等待5秒...")
            time.sleep(5)
            process.terminate()
            logger.info("应用测试启动成功")
        except Exception as e:
            logger.error(f"应用测试启动失败: {str(e)}")
            return False
    
    return True


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="STK应用打包工具")
    
    parser.add_argument("--clean", action="store_true", help="清理旧的构建文件")
    parser.add_argument("--debug", action="store_true", help="启用详细日志输出(使用--log-level=DEBUG)")
    parser.add_argument("--onedir", action="store_true", help="生成目录结构而非单一可执行文件")
    parser.add_argument("--console", action="store_true", help="显示控制台窗口")
    parser.add_argument("--test-run", action="store_true", help="打包后测试运行")
    parser.add_argument("--platform-specific", action="store_true", help="生成平台特定的规格文件")
    parser.add_argument("--spec-file", type=str, help="指定要使用的spec文件")
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志
    logger = setup_logging(debug=args.debug)
    
    logger.info(f"=== STK打包工具 - 开始于 {datetime.now()} ===")
    logger.info(f"Python版本: {platform.python_version()}")
    logger.info(f"系统平台: {platform.system()} {platform.release()}")
    
    # 检查是否在虚拟环境中运行
    if not activate_venv():
        return 1
    
    # 检查依赖
    if not check_dependencies(logger):
        return 1
    
    # 运行PyInstaller
    if not run_pyinstaller(logger, args):
        return 1
    
    # 验证构建结果
    if not verify_build(logger, args):
        return 1
    
    logger.info("=== 打包成功完成! ===")
    return 0


if __name__ == "__main__":
    sys.exit(main()) 