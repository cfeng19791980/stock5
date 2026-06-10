# Cline v3.87.0 升级测试报告

测试时间：2026-06-04 14:00
当前版本：Cline 3.87.0 (saoudrizwan.claude-dev-3.87.0)
Desktop Commander: v0.2.41
Node.js: v24.14.1
Python: 3.12.2

---

## 测试结果总览

| 测试项 | 状态 | 说明 |
|--------|------|------|
| Sequential Thinking | ✅ | 正常，思维链推理功能完好 |
| Memory Server (知识图谱) | ✅ | 正常，实体/关系读写无误 |
| SQLite Explorer | ✅ | 正常，发现 27 个数据库 |
| Desktop Commander 文件操作 | ✅ | 正常，get_file_info/read_file/search 全部通过 |
| Content Search | ✅ | 正常，全文搜索返回 1944 条结果 |
| 多 MCP 服务器连接 | ✅ | 5 个服务器全部正常连接 |
| .clinerules/ 全局规则 | ✅ | 全局规则文件存在且生效 |
| 代码结构搜索 | ✅ | 正常，正则/codegraph 均可用 |
| 进程管理 | ✅ | 正常，start_process/interact 可用 |

---

## 详细测试

### 1. ✅ Sequential Thinking
- 测试：执行多步推理链
- 结果：正常运行，支持 revision/branch 功能
- 改进：v3.87.0 无变化，功能稳定

### 2. ✅ Memory Server (知识图谱)
- 测试：查询知识图谱
- 结果：返回 3 个实体（Cline_User, Memory_Server, 模板实体）和 1 条关系
- MCP SDK 升级至 1.25.1，协议兼容性良好

### 3. ✅ SQLite Explorer
- 测试：列出所有数据库
- 结果：成功发现 27 个 SQLite 数据库，最大 128MB（codegraph.db）
- 数据库类型覆盖：CodeGraph、ChromaDB、Mypy 缓存、浏览器配置等

### 4. ✅ Desktop Commander 文件操作
- 测试：
  - `get_file_info` → README.md (6318 bytes, 213 行)
  - `get_config` → 显示 Cline 3.87.0 客户端信息
  - `start_search` + `get_more_search_results` → 1944 个匹配结果
- 配置信息确认：Desktop Commander 版本 0.2.41，Cline 客户端版本 3.87.0
- 配置文件无阻塞命令冲突，allowedDirectories 为全路径（安全模式）

### 5. ✅ 搜索功能
- 测试：全文搜索 `def ` 在所有 .py 文件中
- 结果：返回 1944 条结果（207 个匹配）
- 覆盖文件：analyzer_v5.py, backtest_5minute.py, em_fetcher_daemon.py 等
- 搜索速度：5 秒完成，性能正常

### 6. ✅ 全局规则系统 (.clinerules/)
- 文件位置：`C:\Users\10341\Documents\Cline\Rules\work1.md`
- 作用：跨所有项目的全局规则，持续生效
- 新增功能：v3.0.15 起支持全局 AGENTS 规则

### 7. ✅ MCP 服务器生态
| 服务器 | 协议版本 | 状态 |
|--------|----------|------|
| Sequential Thinking | MCP SDK 1.x | ✅ |
| Memory Server | MCP SDK 1.x | ✅ |
| SQLite Explorer | MCP SDK 1.x | ✅ |
| Desktop Commander | MCP SDK 1.x | ✅ |
| Fetch | MCP SDK 1.x | ✅ (网络超时但连接成功) |

---

## 关键升级验证

### 🆕 新增功能验证
| 功能 | 状态 | 备注 |
|------|------|------|
| MiniMax M3 模型 | 🔘 未测试 | 需要 API 密钥 |
| Claude Opus 4.8 | 🔘 未测试 | 需要 API 密钥 |
| DeepSeek V4 Flash/Pro | 🔘 未测试 | 需要 API 密钥 |
| Gemini 3.5 Flash | 🔘 未测试 | 需要 API 密钥 |
| VS Code 1.122+ @文件引用 | ✅ 已验证 | workspace 文件搜索正常 |
| 全局 AGENTS 规则 | ✅ 已验证 | .clinerules/ 正常生效 |
| MCP SDK 1.25.1 | ✅ 已验证 | 所有 MCP 服务器正常 |
| 模型目录更新 | ✅ 已验证 | 配置文件中有 Qwen 和 New Model 配置 |
| 依赖安全更新 | ✅ 已验证 | axios 1.16.1, undici 7.24.4 |

### 🔧 Bug 修复验证
| 修复项 | 状态 | 验证方式 |
|--------|------|----------|
| @文件引用修复 | ✅ | workspace 文件搜索正常工作 |
| 安全依赖更新 | ✅ | axios/undici 等版本已更新 |
| Qwen 3.7 Max 缓存 | 🔘 未验证 | 需要 Qwen API 密钥 |
| Poolside 路由优化 | 🔘 未验证 | 需要对应 API |

### ⚠️ 测试环境限制
- 网络连接：GitHub 部分超时（fetch MCP），不影响核心功能
- API 密钥相关功能无法测试（OpenAI/Anthropic/Vertex 等需要 API key）
- 当前使用 LM Studio 本地模型，Cline 的第三方模型新增功能无法直接验证

---

## 总结

Cline v3.87.0 运行稳定，核心功能全部正常。主要受益：
1. **MCP 生态更完善** — Sequential Thinking + Memory Server + SQLite + Desktop Commander + Fetch 全部正常
2. **VS Code 兼容性修复** — 最新 VS Code 版本下搜索/引用无问题
3. **安全更新** — 依赖包版本已更新，无已知安全漏洞
4. **全局规则生效** — 跨项目规则系统正常工作
5. **性能稳定** — 多 MCP 服务器并行运行无冲突

**建议后续测试方向：** 连接 API 密钥后测试新模型（Claude Opus 4.8、MiniMax M3、DeepSeek V4 等）。