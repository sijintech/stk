import os
import sys
import subprocess
import ctypes
import platform


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def setup_ollama_for_remote():
    """配置Ollama以接受远程连接"""
    if platform.system() != "Windows":
        print("此脚本仅适用于Windows系统")
        return

    if not is_admin():
        print("需要管理员权限来配置Ollama服务和防火墙规则")
        print(
            "请右键点击PowerShell或命令提示符，选择'以管理员身份运行'，然后重新运行此脚本"
        )
        return

    print("开始配置Ollama以接受远程连接...")

    # 1. 设置环境变量
    try:
        subprocess.run(["setx", "OLLAMA_HOST", "0.0.0.0:11435"], check=True)
        print("✅ 已设置OLLAMA_HOST环境变量为0.0.0.0:11435")
    except subprocess.SubprocessError as e:
        print(f"❌ 设置环境变量失败: {str(e)}")

    # 2. 添加防火墙规则
    try:
        subprocess.run(
            [
                "powershell",
                "-Command",
                "New-NetFirewallRule -DisplayName 'Ollama Service' -Direction Inbound -Protocol TCP -LocalPort 11435 -Action Allow",
            ],
            check=True,
        )
        print("✅ 已添加Windows防火墙规则")
    except subprocess.SubprocessError as e:
        print(f"❌ 添加防火墙规则失败: {str(e)}")

    # 3. 检查Ollama进程并重启
    try:
        # 检查是否有Ollama进程
        result = subprocess.run(
            [
                "powershell",
                "-Command",
                "Get-Process -Name 'ollama' -ErrorAction SilentlyContinue",
            ],
            capture_output=True,
            text=True,
        )

        if "ollama" in result.stdout.lower():
            print("找到正在运行的Ollama进程，需要重启以应用新设置")
            try:
                subprocess.run(
                    ["powershell", "-Command", "Stop-Process -Name 'ollama' -Force"],
                    check=True,
                )
                print("✅ 已停止Ollama进程")
                print("请手动重启Ollama应用程序以应用新设置")
            except subprocess.SubprocessError as e:
                print(f"❌ 停止Ollama进程失败: {str(e)}")
        else:
            print("未找到正在运行的Ollama进程，请启动Ollama应用程序")
    except Exception as e:
        print(f"检查Ollama进程失败: {str(e)}")

    print("\n配置完成！请确保:")
    print("1. 重启Ollama应用程序以应用新设置")
    print("2. 运行验证工具确认配置是否生效")
    print("3. 如果仍然无法远程连接，请检查网络路由器或其他防火墙设置")


if __name__ == "__main__":
    setup_ollama_for_remote()
