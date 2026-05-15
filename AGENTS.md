# BOM 智能库存管理系统 - Agent 指南

## 项目概述

电子元器件库存管理工具。两种使用方式：
1. **CLI** (`main.py`)：本地批量导入、查询
2. **飞书机器人** (`feishu_bot.py`)：Flask Webhook 服务，聊天中上传 BOM、查询物料

无构建系统，直接运行。无单元测试。

## 环境配置

### 密钥（必须）

所有密钥走环境变量，不再硬编码。本地开发用 `.env` 文件：

```bash
cp .env.example .env
# 编辑 .env 填入真实值
```

```env
LARK_APP_ID=cli_xxx
LARK_APP_SECRET=xxx
OPENAI_API_KEY=sk-or-v1-xxx
OPENAI_MODEL=gpt-3.5-turbo
PORT=5000
```

### 安装依赖

```bash
pip install -r requirements.txt
```

### 权限文件

- `data/authorized_users.json`：有删除权限的用户名列表
- `data/admins.json`：超级管理员列表（可执行 `授权` / `取消授权`）

## CLI 命令

```bash
# 上传 BOM（Excel/CSV）
py main.py upload BOM.xlsx --ai --export csv

# 查询物料（子串匹配所有字段）
py main.py query "STM32F103"

# 查询物料归属
py main.py who GRM188R60J476ME15D

# 列出库存
py main.py list --limit 20

# 导出
py main.py export --format csv

# 查看上传历史
py main.py history --limit 10
```

## 飞书机器人启动

### Windows

```powershell
# 1. 启动 ngrok（需先配置 authtoken）
ngrok config add-authtoken xxx
ngrok http 5000
# 复制 https URL 到飞书开发者平台 Webhook 配置

# 2. 启动机器人
py feishu_bot.py
```

### Linux

```bash
# 安装 ngrok
sudo apt install ngrok -y
# 或 wget https://bin.equinox.io/.../ngrok-v3-stable-linux-amd64.tgz

# 配置 authtoken（一次即可）
ngrok config add-authtoken xxx

# 启动
ngrok http 5000
# 新终端
python3 feishu_bot.py
```

## 飞书聊天命令

| 命令 | 功能 |
|------|------|
| 发送文件 | 上传 BOM，进入多步流程 |
| `录入` | 手动批量录入（先输封装，再逐条输容值） |
| `查询 <关键词>` | 搜索库存 |
| `历史` | 查看上传历史 |
| `删除 <序号/时间戳>` | 删除指定批次（需权限） |
| `授权 <用户名>` | 授予删除权限（仅超级管理员） |
| `谁有 <料号>` | 查物料归属 |
| `库存` | 列出全部库存 |
| `帮助` | 显示帮助 |

## 关键架构

### 多步上传流程
```
文件上传 → STATE_UPLOADED
  → 用户选"加入库存"(MODE_ADD) 或 "摘取物料"(MODE_EXTRACT)
    → MODE_ADD: 直接入库，同步云表格
    → MODE_EXTRACT: 对比库存 → STATE_CONFIRMING
      → 选"移除重复项" → 生成精简 BOM Excel，发送到聊天
      → 选"保留所有" → 不做处理
```

### 手动录入流程（两阶段）
```
录入 → STATE_MANUAL_PACKAGE（输入统一封装，如 0402）
  → STATE_MANUAL_INPUT（逐条输入容值：10kΩ, 47uF...）
    → "完成" → 入库 + 同步云表格
    → "取消" → 放弃
```

### 数据字段（内部使用中文键名）
| 字段 | 说明 |
|------|------|
| `名称` | 组件类型（电阻/电容/芯片等） |
| `料号` | Manufacturer Part，去重主键；手动录入时自动生成 |
| `封装` | Footprint |
| `容值` | Value（阻值/容值等参数） |
| `数量` | Quantity，合并累加 |
| `主人` | 上传者/归属人 |
| `生产商` | Manufacturer |
| `供应商` | Supplier |

### 数据库存储格式
```json
{
  "parts": {"<料号>": {"name": "...", "stock": 5, "owner": "...", ...}},
  "bom": [{"designator": "C1", "part": "<料号>"}],
  "history": [{"time": "...", "owner": "...", "count": 47, "added_items": {"<料号>": 数量}}]
}
```

### 文件职责
| 文件 | 作用 |
|------|------|
| `feishu_bot.py` | Flask Webhook、命令解析、消息发送 |
| `inventory.py` | 库存 CRUD、历史记录、回滚删除 |
| `conversation.py` | 多步会话状态机（5 个 STATE） |
| `bom_matcher.py` | BOM 对比、去重、生成精简 Excel |
| `cloud_sheet.py` | 飞书多维表格 REST API 同步 |
| `component_types.py` | 集中式组件类型映射 |
| `ai_processor.py` | OpenRouter AI 查询兜底 |
| `bom_processor.py` | Excel/CSV 读取、按 Designator 前缀识别类型 |
| `config.py` | 路径、密钥配置，支持 `.env` 加载 |

## 已知陷阱

1. **`smart_query` 逻辑问题**：当查询不含封装关键词（0402/0603 等）也不含容值匹配时，会返回全部库存（`matched_package` 和 `matched_value` 默认为 `True`）。

2. **ngrok 需要 authtoken**：Linux 上首次使用需 `ngrok config add-authtoken <token>`，否则报 `ERR_NGROK_4018`。

3. **临时文件清理**：`feishu_bot.py` 的 `download_file()` 使用 `delete=False`，但 `handle_file_upload()` 会清理。中断时可能残留。

4. **Flask 开发服务器**：`app.run()` 非生产级，无 HTTPS。

5. **编码处理**：`main.py` 第 6 行强制设置 `sys.stdout` 为 utf-8，避免 Windows 控制台乱码。

6. **手动录入命令拦截**：手录模式下输入 `查询 xxx`、`历史` 等命令会被拦截并提示先发送"完成"。用 `first_word` 匹配而非全字匹配。

7. **旧历史记录无法删除**：2026-04-25 ~ 2026-04-26 的历史记录没有 `added_items` 字段，删除时提示"旧记录不支持删除"。

## 开发约定

- **命名混合中英文**：内部数据字段用中文（`名称`, `封装`, `容值`, `料号`, `主人`），类名/方法名用英文
- **静态方法优先**：`BOMProcessor` 全静态方法，无实例状态
- **异常降级**：AI 处理失败捕获异常，降级本地逻辑，不阻断主流程
- **路径处理**：统一 `pathlib.Path`，根目录由 `config.BASE_DIR` 决定

## 测试

无自动化测试。手动测试：
- `test_query.py`：4 条 AI 查询样例，验证 OpenRouter 连接
- `test_file_upload.md`：飞书文件上传手动测试步骤

## 重置库存

```bash
# Windows
Remove-Item F:\BOM\data\inventory.json -Force
py -c "from pathlib import Path; import os; os.chdir('F:/BOM'); f=list(Path('.').glob('*.xlsx'))[0]; from bom_processor import BOMProcessor; from inventory import InventoryManager; items=BOMProcessor.read_file(f.name); InventoryManager().add_items(items); print(f'OK {len(items)} items')"

# Linux
rm ~/BOM/data/inventory.json
python3 -c "from pathlib import Path; import os; os.chdir('/home/user/BOM'); f=list(Path('.').glob('*.xlsx'))[0]; from bom_processor import BOMProcessor; from inventory import InventoryManager; items=BOMProcessor.read_file(f.name); InventoryManager().add_items(items); print(f'OK {len(items)} items')"
```
