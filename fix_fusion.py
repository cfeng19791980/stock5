from pathlib import Path

f = 'E:/stock5/run/llm_factors/factor_fusion.py'
content = Path(f).read_text(encoding='utf-8')

# 替换硬编码
old = 'DB_PATH = r"E:\\stock5\\stocks.db"'
new = 'DB_PATH = str(PROJECT_DIR / "stocks.db")'

content = content.replace(old, new)

Path(f).write_text(content, encoding='utf-8')
print('Done')