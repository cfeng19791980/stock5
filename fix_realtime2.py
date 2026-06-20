from pathlib import Path

f = 'E:/stock5/run/realtime_fetcher.py'
content = Path(f).read_text(encoding='utf-8')

# 替换硬编码
old = "filepath: str = r'E:\\stock5\\logs\\fetcher_metrics.json'"
new = """filepath: str = None
        if filepath is None:
            filepath = str(PROJECT_DIR / "logs" / "fetcher_metrics.json")"""

content = content.replace(old, new)

Path(f).write_text(content, encoding='utf-8')
print('Done')