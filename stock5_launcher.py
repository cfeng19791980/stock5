# -*- coding: utf-8 -*-
"""
stock5_launcher.py - Stock5 Python启动脚本（简化版）
功能：启动Web服务器 + 数据采集
"""

import sys
import os
import subprocess
import psutil
import time
from pathlib import Path

# 项目目录
PROJECT_DIR = Path(__file__).parent.absolute()
PID_FILE = PROJECT_DIR / "collection.pid"
WEB_PID_FILE = PROJECT_DIR / "web_server.pid"
LOG_DIR = PROJECT_DIR / "logs"

# 确保日志目录存在
LOG_DIR.mkdir(exist_ok=True)

def write_pid(pid_file, pid):
    """写入PID文件"""
    with open(pid_file, 'w', encoding='utf-8') as f:
        f.write(str(pid))

def read_pid(pid_file):
    """读取PID文件"""
    if not pid_file.exists():
        return None
    try:
        with open(pid_file, 'r', encoding='utf-8') as f:
            return int(f.read().strip())
    except:
        return None

def is_process_running(pid):
    """检查进程是否运行"""
    if pid is None:
        return False
    try:
        return psutil.pid_exists(pid)
    except:
        return False

def start_web_server():
    """启动Web服务器"""
    print("\n[1] 启动Web服务器...")
    
    # 检查是否已运行
    web_pid = read_pid(WEB_PID_FILE)
    if is_process_running(web_pid):
        print(f"  ⚠ Web服务器已运行 (PID: {web_pid})")
        return web_pid
    
    # 启动进程
    try:
        log_file = LOG_DIR / "web_server.log"
        proc = subprocess.Popen(
            [sys.executable, "web_server.py"],
            cwd=PROJECT_DIR,
            stdout=open(log_file, 'a', encoding='utf-8'),
            stderr=subprocess.STDOUT
        )
        
        write_pid(WEB_PID_FILE, proc.pid)
        print(f"  ✓ Web服务器已启动 (PID: {proc.pid})")
        print(f"  访问地址: http://127.0.0.1:5005")
        
        return proc.pid
    except Exception as e:
        print(f"  ❌ 启动Web服务器失败: {e}")
        return None

def start_data_collection():
    """启动数据采集"""
    print("\n[2] 启动数据采集...")
    
    # 检查是否已运行
    collect_pid = read_pid(PID_FILE)
    if is_process_running(collect_pid):
        print(f"  ⚠ 数据采集已运行 (PID: {collect_pid})")
        return collect_pid
    
    # 启动进程
    try:
        proc = subprocess.Popen(
            [sys.executable, "realtime_fetcher.py", "--daemon", "--interval", "5"],
            cwd=PROJECT_DIR
        )
        
        # 等待PID文件生成
        time.sleep(2)
        
        collect_pid = read_pid(PID_FILE)
        if collect_pid:
            print(f"  ✓ 数据采集已启动 (PID: {collect_pid})")
            print(f"  采集频率: 每5分钟")
        else:
            print(f"  ⚠ PID文件未生成，请检查日志")
        
        return collect_pid
    except Exception as e:
        print(f"  ❌ 启动数据采集失败: {e}")
        return None

def stop_all_services():
    """停止所有服务"""
    print("\n停止所有服务...")
    
    # 停止Web服务器
    web_pid = read_pid(WEB_PID_FILE)
    if web_pid and is_process_running(web_pid):
        try:
            proc = psutil.Process(web_pid)
            proc.terminate()
            print(f"  ✓ Web服务器已停止 (PID: {web_pid})")
        except:
            print(f"  ⚠ 停止Web服务器失败")
    else:
        print("  Web服务器未运行")
    
    if WEB_PID_FILE.exists():
        WEB_PID_FILE.unlink()
    
    # 停止数据采集
    collect_pid = read_pid(PID_FILE)
    if collect_pid and is_process_running(collect_pid):
        try:
            proc = psutil.Process(collect_pid)
            proc.terminate()
            print(f"  ✓ 数据采集已停止 (PID: {collect_pid})")
        except:
            print(f"  ⚠ 停止数据采集失败")
    else:
        print("  数据采集未运行")
    
    if PID_FILE.exists():
        PID_FILE.unlink()
    
    print("\n✓ 所有服务已停止")

def start_all_services():
    """启动所有服务"""
    print("=" * 70)
    print("Stock5 - 启动所有服务")
    print("=" * 70)
    
    web_pid = start_web_server()
    collect_pid = start_data_collection()
    
    print("\n" + "=" * 70)
    print("服务状态:")
    print(f"  Web服务器: {'运行中' if is_process_running(web_pid) else '未启动'} (PID: {web_pid or 'N/A'})")
    print(f"  数据采集: {'运行中' if is_process_running(collect_pid) else '未启动'} (PID: {collect_pid or 'N/A'})")
    print("=" * 70)
    
    print("\n访问地址:")
    print(f"  Web界面: http://127.0.0.1:5005")
    print(f"  日志目录: {LOG_DIR}")
    print("=" * 70)

def show_status():
    """显示服务状态"""
    print("\n" + "=" * 70)
    print("Stock5 - 服务状态")
    print("=" * 70)
    
    # Web服务器状态
    web_pid = read_pid(WEB_PID_FILE)
    web_running = is_process_running(web_pid)
    
    print(f"\nWeb服务器:")
    print(f"  PID: {web_pid or 'N/A'}")
    print(f"  状态: {'✓ 运行中' if web_running else '❌ 未运行'}")
    if web_running:
        print(f"  访问: http://127.0.0.1:5005")
    
    # 数据采集状态
    collect_pid = read_pid(PID_FILE)
    collect_running = is_process_running(collect_pid)
    
    print(f"\n数据采集:")
    print(f"  PID: {collect_pid or 'N/A'}")
    print(f"  状态: {'✓ 运行中' if collect_running else '❌ 未运行'}")
    if collect_running:
        print(f"  频率: 每5分钟")
    
    print("\n" + "=" * 70)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Stock5服务启动脚本')
    parser.add_argument('--start', action='store_true', help='启动所有服务')
    parser.add_argument('--stop', action='store_true', help='停止所有服务')
    parser.add_argument('--status', action='store_true', help='查看服务状态')
    parser.add_argument('--restart', action='store_true', help='重启所有服务')
    
    args = parser.parse_args()
    
    if args.start:
        start_all_services()
    elif args.stop:
        stop_all_services()
    elif args.status:
        show_status()
    elif args.restart:
        stop_all_services()
        time.sleep(2)
        start_all_services()
    else:
        # 默认启动
        start_all_services()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断，退出...")
        sys.exit(0)