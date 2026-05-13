# BOM 智能库存管理系统 - Agent 指南

## 项目概述

电子元器件库存管理工具。两种使用方式：
1. **CLI** (`main.py`)：本地批量导入、查询
2. **飞书机器人** (`feishu_bot.py`)：Flask Webhook 服务，聊天中上传 BOM、查询物料

无构建系统，直接 `py <脚本>` 运行。无单元测试。

## 安装依赖

```bash
pip install -r requirements.txt
```

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

## 飞书机器人启动顺序

```bash
# 1. 必须先启动 ngrok（项目自带 ngrok.exe）
.\ngrok.exe http 5000

# 2. 启动机器人
py feishu_bot.py
```

环境变量：`LARK_APP_ID`, `LARK_APP_SECRET`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `PORT`

## 关键架构

### 数据流向
- `bom_processor.py` → 读取 Excel/CSV，按 `Designator` 前缀识别组件类型
- `inventory.py` → 读写 `data/inventory.json`，按 `料号` 去重合并
- `ai_processor.py` → OpenRouter API，失败时降级到本地逻辑

### 数据字段（内部使用中文键名）
| 字段 | 说明 |
|------|------|
| `名称` | 组件类型（电阻/电容/芯片等） |
| `料号` | Manufacturer Part，去重主键 |
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
  "history": [{"time": "...", "owner": "...", "count": 47}]
}
```

## 已知陷阱

1. **`smart_query` 逻辑问题**：当查询不含封装关键词（0402/0603 等）也不含容值匹配时，会返回全部库存（`matched_package` 和 `matched_value` 默认为 `True`）。

2. **硬编码 API 密钥**：`config.py` 有默认密钥，生产环境必须通过环境变量覆盖。

3. **临时文件清理**：`feishu_bot.py` 的 `download_file()` 使用 `delete=False`，但 `handle_file_upload()` 会清理。中断时可能残留。

4. **Flask 开发服务器**：`app.run()` 非生产级，无 HTTPS。

5. **编码处理**：`main.py` 第 6 行强制设置 `sys.stdout` 为 utf-8，避免 Windows 控制台乱码。

## 重置库存

```bash
Remove-Item F:\BOM\data\inventory.json -Force
py -c "from pathlib import Path; import os; os.chdir('F:/BOM'); f=list(Path('.').glob('*.xlsx'))[0]; from bom_processor import BOMProcessor; from inventory import InventoryManager; items=BOMProcessor.read_file(f.name); InventoryManager().add_items(items); print(f'OK {len(items)} items')"
```

## 开发约定

- **命名混合中英文**：内部数据字段用中文（`名称`, `封装`, `容值`, `料号`, `主人`），类名/方法名用英文
- **静态方法优先**：`BOMProcessor` 全静态方法，无实例状态
- **异常降级**：AI 处理失败捕获异常，降级本地逻辑，不阻断主流程
- **路径处理**：统一 `pathlib.Path`，根目录由 `config.BASE_DIR` 决定

## 测试

无自动化测试。手动测试：
- `test_query.py`：4 条 AI 查询样例，验证 OpenRouter 连接
- `test_file_upload.md`：飞书文件上传手动测试步骤
