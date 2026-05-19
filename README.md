# BOM Manager

电子元器件库存管理工具。支持 CLI 批量操作和飞书机器人聊天交互。

## 功能

- **BOM 上传** — 读取 Excel/CSV 格式的 BOM 文件，自动解析物料清单
- **AI 整理** — 可选 AI 辅助去重、标准化、分类（OpenRouter）
- **库存管理** — SQLite 存储，支持增删查改、历史记录、回滚删除
- **智能查询** — 按类型+容值+封装三层过滤，支持连接器针数匹配
- **飞书机器人** — 聊天中上传文件、查库存、手动录入物料
- **库存导出** — 导出为 Excel 或 CSV
- **飞书多维表格同步** — 同步库存到飞书 Bitable

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 编辑填入密钥
```

**CLI 模式：**
```bash
py main.py upload BOM.xlsx --ai
py main.py query "STM32F103"
py main.py list --limit 20
```

**飞书机器人：**
```bash
ngrok http 5000
py feishu_bot.py
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `LARK_APP_ID` | 飞书应用 ID |
| `LARK_APP_SECRET` | 飞书应用 Secret |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key（OpenAI / OpenRouter / 本地 LLM） |
| `OPENAI_BASE_URL` | API 地址（默认 `https://api.openai.com/v1`） |
| `OPENAI_MODEL` | AI 模型（默认 gpt-3.5-turbo） |

## 项目结构

```
├── main.py              # CLI 入口
├── feishu_bot.py        # 飞书机器人 Flask 服务
├── inventory.py         # 库存 CRUD（SQLite）
├── conversation.py      # 多步会话状态机
├── bom_processor.py     # Excel/CSV 解析
├── bom_matcher.py       # BOM 对比去重
├── ai_processor.py      # AI 查询兜底
├── cloud_sheet.py       # 飞书多维表格同步
├── component_types.py   # 组件类型映射
└── config.py            # 配置与路径管理
```

## 技术栈

Python + Flask + SQLite + openpyxl + lark-oapi
