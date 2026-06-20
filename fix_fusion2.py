from pathlib import Path

f = 'E:/stock5/run/llm_factors/factor_fusion.py'
content = Path(f).read_text(encoding='utf-8')

# 修复
content = content.replace(
    "DB_PATH = r'E:\\stock5\\stocks.db'",
    "DB_PATH = str(PROJECT_DIR / 'stocks.db')"
)

Path(f).write_text(content, encoding='utf-8')
print('Done')