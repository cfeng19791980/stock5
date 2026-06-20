# -*- coding: utf-8 -*-
"""
批量修复 Stock5 硬编码路径问题
将 E:\stock5 改为相对路径
"""
import re
from pathlib import Path

def fix_file(filepath):
    """修复单个文件的硬编码路径"""
    print(f"处理: {filepath}")
    
    try:
        content = Path(filepath).read_text(encoding='utf-8')
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        return False
    
    original = content
    modified = content
    
    # 需要替换的模式
    replacements = [
        # 基础路径替换
        (r'DB_PATH = r"([^"]*stocks\.db)"', r'DB_PATH = str(PROJECT_DIR / "stocks.db")'),
        (r'CSV_PATH = r"([^"]*波段股票Top30\.csv)"', r'CSV_PATH = str(PROJECT_DIR / "波段股票Top30.csv")'),
        (r'OUTPUT_JSON = r"([^"]*result_v5\.json)"', r'OUTPUT_JSON = str(PROJECT_DIR / "result_v5.json")'),
        (r'MODEL_CACHE_DIR = r"([^"]*model_cache_v6)"', r'MODEL_CACHE_DIR = str(PROJECT_DIR / "model_cache_v6")'),
        (r'LOG_FILE = r"([^"]*logs\\[^"]+\.log)"', r'LOG_FILE = str(PROJECT_DIR / "logs" / "\1")'.replace('PROJECT_DIR / "logs" / "\\1"', 'PROJECT_DIR / "logs" / "collection.log"')),
        
        # realtime_fetcher.py 特殊处理
        (r'LOG_DIR = r"([^"]*logs)"', r'LOG_DIR = str(PROJECT_DIR / "logs")'),
        (r'filepath: str = r"([^"]*fetcher_metrics\.json)"', r'filepath: str = str(PROJECT_DIR / "logs" / "fetcher_metrics.json")'),
        
        # 移除旧的 PROJECT_DIR 定义（如果已经有相对路径版本）
        (r'PROJECT_DIR = pathlib\.Path\(\)\.parent\.absolute\(\).*?\n', ''),
    ]
    
    # 检查是否已经修复过
    if 'PROJECT_DIR = pathlib.Path(__file__).parent' in content:
        print(f"  ⏭️  已修复，跳过")
        return True
    
    # 添加相对路径定义（在第一个import之后）
    # 查找 import 语句后的位置
    import_pattern = r'^(import |from .*? import )'
    matches = list(re.finditer(import_pattern, content, re.MULTILINE))
    
    if matches:
        # 在最后一个标准import之后添加
        insert_pos = matches[-1].end()
        # 找到这一行的结束
        line_end = content.find('\n', insert_pos)
        if line_end != -1:
            insert_pos = line_end + 1
            
            # 检查是否需要添加 pathlib import
            if 'import pathlib' not in content[:insert_pos]:
                insert_text = '\nimport pathlib\n'
            else:
                insert_text = '\n'
            
            insert_text += '\n# 使用相对路径\nPROJECT_DIR = pathlib.Path(__file__).parent.absolute()\n'
            content = content[:insert_pos] + insert_text + content[insert_pos:]
            modified = content
    
    # 执行替换
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    # 特殊修复: realtime_fetcher.py 的 filepath 参数
    content = re.sub(
        r"filepath: str = r'.*?fetcher_metrics\.json'",
        "filepath: str = str(PROJECT_DIR / 'logs' / 'fetcher_metrics.json')",
        content
    )
    
    # 特殊修复: LOG_FILE 路径
    content = re.sub(
        r"LOG_FILE = str\(PROJECT_DIR / \"logs\" / \"logs\" /",
        r"LOG_FILE = str(PROJECT_DIR / \"logs\" /",
        content
    )
    
    if content != original:
        try:
            Path(filepath).write_text(content, encoding='utf-8')
            print(f"  ✅ 已修复")
            return True
        except Exception as e:
            print(f"  ❌ 写入失败: {e}")
            return False
    else:
        print(f"  ⏭️  无需修复")
        return True

def main():
    base = Path("E:/stock5/run")
    
    files_to_fix = [
        # 核心文件
        base / "analyzer_v5.py",
        base / "analyzer_v5_minute.py",
        base / "realtime_fetcher.py",
        base / "em_fetcher_daemon.py",
        base / "check_data_integrity.py",
        base / "web_server.py",
        
        # LLM因子
        base / "llm_factors" / "factor_runner.py",
        base / "llm_factors" / "factor_fusion.py",
        
        # GUI
        base / "stock5_gui_launcher.py",
    ]
    
    print("=" * 50)
    print("Stock5 硬编码路径批量修复")
    print("=" * 50)
    
    success = 0
    failed = 0
    
    for f in files_to_fix:
        if f.exists():
            if fix_file(f):
                success += 1
            else:
                failed += 1
        else:
            print(f"跳过: {f} (不存在)")
    
    print("=" * 50)
    print(f"完成: {success} 成功, {failed} 失败")
    print("=" * 50)

if __name__ == "__main__":
    main()