# -*- coding: utf-8 -*-
"""
semantic_memory.py — Stock5 语义记忆引擎
基于 LM Studio BGE-M3 向量嵌入 + 余弦相似度检索

功能：
  1. store(text) — 记忆文本 → BGE-M3 嵌入 → 存入向量库
  2. search(query, top_k=5) — 查询 → 向量化 → cosine 相似度 → Top-K 召回
  3. list() — 列出所有记忆
  4. clear() — 清空记忆

存储位置：用户目录/.codex/skills/semantic-memory/
"""

import numpy as np
import pickle
import os
import json
import requests
from datetime import datetime
from pathlib import Path

# ── 配置 ──
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
STORAGE_DIR = Path.home() / ".codex" / "skills" / "semantic-memory"
STORAGE_FILE = STORAGE_DIR / "vector_store.pkl"
TOP_K_DEFAULT = 5

# ── 向量库结构 ──
# {
#   "texts": ["记忆��本1", "记忆文本2", ...],
#   "vectors": np.array([[0.1, 0.2, ...], ...]),  # shape: (n, 1024)
#   "metadata": [
#       {"timestamp": "...", "project": "...", "type": "..."},
#       ...
#   ]
# }

def _ensure_storage():
    """确保存储目录和文件存在"""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE_FILE.exists():
        _save_store({"texts": [], "vectors": np.empty((0, 1024)), "metadata": []})

def _load_store():
    """加载向量库"""
    _ensure_storage()
    try:
        with open(STORAGE_FILE, "rb") as f:
            data = pickle.load(f)
        # 兼容旧格式：补全缺失字段
        if "metadata" not in data:
            data["metadata"] = [{} for _ in data["texts"]]
        return data
    except (EOFError, pickle.UnpicklingError, FileNotFoundError):
        return {"texts": [], "vectors": np.empty((0, 1024)), "metadata": []}

def _save_store(data):
    """保存向量库"""
    with open(STORAGE_FILE, "wb") as f:
        pickle.dump(data, f)

def _embed(text: str) -> np.ndarray:
    """调用 LM Studio BGE-M3 获取文本向量"""
    resp = requests.post(
        LM_STUDIO_URL,
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    vec = resp.json()["data"][0]["embedding"]
    return np.array(vec, dtype=np.float32)

def _normalize(v: np.ndarray) -> np.ndarray:
    """L2 归一化"""
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v

def store(text: str, metadata: dict = None) -> dict:
    """存储一条记忆
    
    Args:
        text: 记忆文本
        metadata: 可选元数据 (timestamp, project, type 等)
    
    Returns:
        {"success": True, "index": n, "dim": 1024}
    """
    vector = _embed(text)
    vector_norm = _normalize(vector)
    
    store = _load_store()
    idx = len(store["texts"])
    store["texts"].append(text)
    store["vectors"] = np.vstack([store["vectors"], vector_norm])
    
    meta = metadata or {}
    if "timestamp" not in meta:
        meta["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    store["metadata"].append(meta)
    
    _save_store(store)
    return {"success": True, "index": idx, "dim": len(vector)}

def search(query: str, top_k: int = TOP_K_DEFAULT) -> list:
    """语义搜索相似记忆
    
    Args:
        query: 搜索文本
        top_k: 返回前 K 条
    
    Returns:
        [{"text": "...", "score": 0.95, "metadata": {...}}, ...]
    """
    store = _load_store()
    if len(store["texts"]) == 0:
        return []
    
    q_vec = _normalize(_embed(query))
    # 余弦相似度 = 归一化向量点积
    scores = store["vectors"] @ q_vec
    
    # 取 Top-K
    top_k = min(top_k, len(scores))
    top_indices = np.argsort(scores)[-top_k:][::-1]
    
    results = []
    for idx in top_indices:
        results.append({
            "text": store["texts"][idx],
            "score": float(scores[idx]),
            "metadata": store["metadata"][idx] if idx < len(store["metadata"]) else {},
        })
    return results

def list_all() -> list:
    """列出所有记忆
    
    Returns:
        [{"index": 0, "text": "...", "metadata": {...}}, ...]
    """
    store = _load_store()
    return [
        {"index": i, "text": store["texts"][i],
         "metadata": store["metadata"][i] if i < len(store["metadata"]) else {}}
        for i in range(len(store["texts"]))
    ]

def clear() -> dict:
    """清空所有记忆"""
    _save_store({"texts": [], "vectors": np.empty((0, 1024)), "metadata": []})
    return {"success": True, "message": "记忆已清空"}

def status() -> dict:
    """查看状态"""
    store = _load_store()
    count = len(store["texts"])
    # 测试 LM Studio 连通性
    try:
        resp = requests.get(LM_STUDIO_URL.replace("/embeddings", "/models"), timeout=5)
        models = resp.json().get("data", [])
        model_info = [m["id"] for m in models] if models else "unknown"
    except Exception as e:
        model_info = f"连接失败: {e}"
    
    return {
        "count": count,
        "model": EMBED_MODEL,
        "storage": str(STORAGE_FILE),
        "lm_studio": model_info,
        "dim": 1024,
    }

# ── CLI 入口 ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python semantic_memory.py <store|search|list|clear|status> [参数...]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "store":
        text = sys.argv[2] if len(sys.argv) > 2 else input("记忆文本: ")
        meta = {}
        if len(sys.argv) > 3:
            try:
                meta = json.loads(sys.argv[3])
            except:
                pass
        result = store(text, meta)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else input("搜索: ")
        top_k = int(sys.argv[3]) if len(sys.argv) > 3 else TOP_K_DEFAULT
        results = search(query, top_k)
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    
    elif cmd == "list":
        items = list_all()
        print(f"共 {len(items)} 条记忆:")
        for item in items:
            print(f"  [{item['index']}] {item['text'][:80]}...")
    
    elif cmd == "clear":
        result = clear()
        print(f"✅ {result['message']}")
    
    elif cmd == "status":
        st = status()
        print(f"模型: {st['model']}")
        print(f"记忆数: {st['count']}")
        print(f"维度: {st['dim']}")
        print(f"存储: {st['storage']}")
        print(f"LM Studio: {st['lm_studio']}")
    
    else:
        print(f"未知命令: {cmd}")
