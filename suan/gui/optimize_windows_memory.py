import os
import sys
import subprocess
import ctypes
import platform
import psutil
import time

def is_admin():
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def optimize_windows_memory():
    """优化Windows系统内存以运行Ollama模型"""
    if platform.system() != "Windows":
        print("此脚本仅适用于Windows系统")
        return
        
    # 显示当前内存状态
    print("系统内存状态:")
    mem = psutil.virtual_memory()
    print(f"总物理内存: {mem.total / (1024**3):.2f} GB")
    print(f"可用物理内存: {mem.available / (1024**3):.2f} GB")
    print(f"内存使用率: {mem.percent}%")
    
    # 检查是否有足够内存
    min_required = 1.5  # GB，比模型需要的稍多一点
    if mem.available / (1024**3) >= min_required:
        print(f"✅ 系统当前有足够内存运行模型 (可用 > {min_required} GB)")
        return
    
    print(f"\n❌ 系统内存不足 (需要至少 {min_required} GB，当前可用 {mem.available / (1024**3):.2f} GB)")
    
    # 1. 尝试释放内存
    print("\n正在尝试释放系统内存...")
    try:
        # 尝试运行垃圾回收
        import gc
        gc.collect()
        
        # 运行系统内存优化命令
        subprocess.run(["powershell", "-Command", "EmptyStandbyList"], shell=True)
    except Exception as e:
        print(f"释放内存过程中出错: {str(e)}")
    
    # 2. 列出大内存进程
    print("\n占用内存较多的进程:")
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            process_memory = proc.info['memory_info'].rss / (1024**2)
            if process_memory > 100:  # 只显示内存占用超过100MB的进程
                processes.append((proc.info['pid'], proc.info['name'], process_memory))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # 按内存使用量排序
    processes.sort(key=lambda x: x[2], reverse=True)
    
    # 显示前10个内存占用高的进程
    for i, (pid, name, memory) in enumerate(processes[:10], 1):
        print(f"{i}. {name} (PID: {pid}): {memory:.2f} MB")
    
    # 3. 检查/配置虚拟内存
    print("\n检查页面文件配置...")
    if is_admin():
        # 如果是管理员，尝试调整页面文件大小
        try:
            # 获取当前页面文件大小
            result = subprocess.run(
                ["wmic", "pagefile", "list", "brief"], 
                capture_output=True, 
                text=True
            )
            print(result.stdout)
            
            # 推荐页面文件大小
            sys_mem = psutil.virtual_memory().total / (1024**3)
            recommended_size = max(int(sys_mem * 1.5), 4)  # 至少是物理内存的1.5倍，最小4GB
            print(f"推荐的页面文件大小: {recommended_size} GB (当前物理内存的1.5倍)")
            
            print("请考虑增加页面文件大小，步骤:")
            print("1. 右键点击"此电脑" -> 属性 -> 高级系统设置")
            print("2. 在"性能"部分点击"设置" -> 高级 -> 更改")
            print("3. 取消选中"自动管理所有驱动器的分页文件大小"")
            print(f"4. 选择系统驱动器，点击"自定义大小"，初始大小和最大大小均设为 {recommended_size * 1024} MB")
            print("5. 点击"设置" -> "确定"，然后重启系统")
        except Exception as e:
            print(f"检查页面文件时出错: {str(e)}")
    else:
        print("需要管理员权限才能查看和调整页面文件设置")
        print("请以管理员身份运行此脚本以获取更详细的建议")
    
    # 4. 其他建议
    print("\n其他解决内存不足的建议:")
    print("1. 关闭不必要的应用程序，特别是上面列出的大内存占用进程")
    print("2. 如果可能，增加服务器物理内存")
    print("3. 尝试使用更小的语言模型，如小于1GB内存需求的模型")
    print("4. 重启服务器以清理内存碎片")
    
    # 重新检查内存状况
    time.sleep(2)
    mem = psutil.virtual_memory()
    print(f"\n内存优化后，当前可用内存: {mem.available / (1024**3):.2f} GB")
    if mem.available / (1024**3) >= min_required:
        print(f"✅ 现在有足够内存运行模型!")
    else:
        print(f"❌ 内存仍然不足，需要进一步优化或使用更小的模型")

if __name__ == "__main__":
    optimize_windows_memory()
