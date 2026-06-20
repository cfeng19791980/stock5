# -*- coding: utf-8 -*-
"""
Stock5 同步脚本 - 研发环境到生产环境
功能：将 src/ 目录同步到 run/，保留运行数据
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

# 配置
PROJECT_DIR = Path(__file__).parent.absolute()
SRC_DIR = PROJECT_DIR / "src"
RUN_DIR = PROJECT_DIR / "run"

# 需要保留的目录/文件（不覆盖）
KEEP_ITEMS = [
    "stocks.db",
    "stocks.db.bak",
    "logs",
    "model_cache_v5",
    "model_cache_v6",
    "collection.pid",
    "em_fetcher.pid",
    "factor_collection.pid",
    "web_server.pid",
    "v6/model_cache_v6",
]

# 需要创建的目录
CREATE_DIRS = [
    "logs",
    "model_cache_v5",
    "model_cache_v6",
    "v6/model_cache_v6",
    "llm_factors",
    "backup",
    "data",
]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def sync_files():
    """同步文件"""
    if not SRC_DIR.exists():
        log(f"❌ 源码目录不存在: {SRC_DIR}")
        return False
    
    log(f"📂 开始同步: {SRC_DIR} → {RUN_DIR}")
    
    # 首次同步：如果 run/ 为空，直接复制整个 src/
    is_first_sync = not list(RUN_DIR.glob("*"))
    
    if is_first_sync:
        log("首次同步，复制全部文件...")
        # 复制整个 src 目录到 run
        import shutil as sh
        for item in SRC_DIR.iterdir():
            if item.name in ['logs', 'model_cache_v5', 'model_cache_v6']:
                continue  # 跳过这些，创建空目录
            if item.is_file():
                sh.copy2(item, RUN_DIR / item.name)
                log(f"  ✅ 复制: {item.name}")
            elif item.is_dir() and item.name not in ['v6']:
                sh.copytree(item, RUN_DIR / item.name, dirs_exist_ok=True)
                log(f"  ✅ 复制: {item.name}/")
        
        # v6 单独处理
        v6_src = SRC_DIR / 'v6'
        v6_dest = RUN_DIR / 'v6'
        v6_dest.mkdir(exist_ok=True)
        for item in v6_src.iterdir():
            if item.is_file():
                sh.copy2(item, v6_dest / item.name)
                log(f"  ✅ v6/{item.name}")
            elif item.is_dir() and item.name != 'model_cache_v6':
                sh.copytree(item, v6_dest / item.name, dirs_exist_ok=True)
                log(f"  ✅ v6/{item.name}/")
        
        # 创建必要目录
        for dir_name in CREATE_DIRS:
            (RUN_DIR / dir_name).mkdir(parents=True, exist_ok=True)
        
        # 复制 stocks.db
        db_src = SRC_DIR / 'stocks.db'
        if db_src.exists():
            sh.copy2(db_src, RUN_DIR / 'stocks.db')
            log(f"  ✅ stocks.db")
        
        log("首次同步完成！")
        return True
    
    # 确保运行目录存在必要子目录
    for dir_name in CREATE_DIRS:
        dir_path = RUN_DIR / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # 同步文件
    copied = 0
    skipped = 0
    
    for item in SRC_DIR.rglob("*"):
        if item.is_file():
            # 计算相对路径
            rel_path = item.relative_to(SRC_DIR)
            
            # 检查是否需要保留
            if any(keep in str(rel_path) for keep in KEEP_ITEMS if "." not in keep):
                # 检查目标文件是否存在
                dest = RUN_DIR / rel_path
                if dest.exists():
                    log(f"  ⏭️ 跳过(保留): {rel_path}")
                    skipped += 1
                    continue
            
            # 复制文件
            dest = RUN_DIR / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # 检查是否需要复制（如果目标不存在或源文件更新）
            need_copy = True
            if dest.exists():
                if dest.stat().st_mtime >= item.stat().st_mtime:
                    need_copy = False
            
            if need_copy:
                shutil.copy2(item, dest)
                copied += 1
                log(f"  ✅ 复制: {rel_path}")
            else:
                skipped += 1
    
    log(f"📊 同步完成: {copied} 文件复制, {skipped} 文件跳过")
    return True

def update_bat_file():
    """更新脚本.bat路径"""
    bat_file = PROJECT_DIR / "run" / "脚本.bat"
    bat_content = '''@echo off
chcp 65001
title Stock Launcher
cd /d "%~dp0"
start /b python web_server.py
start /b python realtime_fetcher.py
start /b stock5_gui_launcher.py
pause
'''
    with open(bat_file, "w", encoding="utf-8") as f:
        f.write(bat_content)
    log("✅ 更新脚本.bat")

def main():
    print("=" * 50)
    print("Stock5 环境同步")
    print("=" * 50)
    
    if not SRC_DIR.exists():
        print(f"❌ 源码目录不存在: {SRC_DIR}")
        print("请先确保 src/ 目录存在并包含源码")
        sys.exit(1)
    
    # 同步文件
    if not sync_files():
        sys.exit(1)
    
    # 更新批处理文件
    update_bat_file()
    
    print("=" * 50)
    print("✅ 同步完成！运行目录: E:\\stock5\\run")
    print("=" * 50)

if __name__ == "__main__":
    main()