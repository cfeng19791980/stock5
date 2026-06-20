# -*- coding: utf-8 -*-
"""
Stock5 初始化脚本 - 将源码复制到 src/ 目录
"""
import os
import shutil
from pathlib import Path

src_root = Path(__file__).parent.absolute()
src_dir = src_root.parent / 'src'

exclude_dirs = {'src','run','.git','.codegraph','__pycache__','backup','logs','graphify-out','model_cache_v5','model_cache_v6','v6','catboost_info','browser-profile','.vscode','.playwright-mcp','autoresearch-win','.continue','.ruff_cache'}
exclude_files = {'stocks.db','stocks.db.bak','collection.pid','em_fetcher.pid','factor_collection.pid','web_server.pid','sync.py'}

print("复制文件到 src/ ...")
for f in src_root.glob('*'):
    if f.is_file():
        if f.name not in exclude_files:
            shutil.copy2(f, src_dir / f.name)
            print(f'  {f.name}')
    elif f.is_dir() and f.name not in exclude_dirs:
        if f.name not in {'model_cache_v5', 'model_cache_v6'}:
            shutil.copytree(f, src_dir / f.name, dirs_exist_ok=True)
            print(f'  {f.name}/')
        else:
            (src_dir / f.name).mkdir(exist_ok=True)
            print(f'  {f.name}/ (空目录)')

# v6 目录单独处理
v6_src = src_root / 'v6'
v6_dest = src_dir / 'v6'
v6_dest.mkdir(exist_ok=True)
for f in v6_src.glob('*'):
    if f.is_file():
        shutil.copy2(f, v6_dest / f.name)
        print(f'  v6/{f.name}')
    elif f.is_dir() and f.name != 'model_cache_v6':
        shutil.copytree(f, v6_dest / f.name, dirs_exist_ok=True)
        print(f'  v6/{f.name}/')

print("\n复制stocks.db ...")
shutil.copy2(src_root / 'stocks.db', src_dir / 'stocks.db')

print("\n✅ src/ 目录初始化完成！")
print(f"文件数: {len(list(src_dir.glob('*')))}")
