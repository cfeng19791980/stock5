# 修复 factor_fusion.py 和 realtime_fetcher.py 的硬编码路径
import re
from pathlib import Path

# 修复 factor_fusion.py
f1 = Path("E:/stock5/run/llm_factors/factor_fusion.py")
c1 = f1.read_text(encoding='utf-8')
c1 = c1.replace("DB_PATH = r'E:\\stock5\\stocks.db'", 'DB_PATH = str(PROJECT_DIR / "stocks.db")')
f1.write_text(c1, encoding='utf-8')
print("factor_fusion.py 修复完成")

# 修复 realtime_fetcher.py
f2 = Path("E:/stock5/run/realtime_fetcher.py")
c2 = f2.read_text(encoding='utf-8')
c2 = c2.replace(r"filepath: str = r'E:\stock5\logs\fetcher_metrics.json'", 
    "filepath: str = None\n        if filepath is None:\n            filepath = str(PROJECT_DIR / 'logs' / 'fetcher_metrics.json')")
f2.write_text(c2, encoding='utf-8')
print("realtime_fetcher.py 修复完成")

# 检查是否还有硬编码
import subprocess
result = subprocess.run(['rg', 'E:\\\\stock5', 'E:/stock5/run', '--type', 'py', '-l'], 
                       capture_output=True, text=True)
if result.stdout.strip():
    print("仍存在硬编码:")
    print(result.stdout)
else:
    print("所有硬编码已修复!")