# BOM 智能库存管理系统

## 功能特性
- 📤 上传 BOM Excel/CSV 文件
- 🤖 AI 智能整理（去重、标准化、分类）
- 📊 输出规范化库存表
- 🔍 查询物料归属（谁有、哪里有）

## 项目结构
```
BOM/
├── main.py           # 主程序入口
├── config.py         # 配置文件
├── bom_processor.py  # BOM处理核心逻辑
├── ai_processor.py   # AI整理模块
├── inventory.py      # 库存管理模块
├── data/             # 数据目录
│   ├── inventory.json  # 库存数据
│   └── history/       # 历史记录
├── requirements.txt  # 依赖
└── README.md         # 说明文档
```

## 依赖
- openpyxl >= 3.0.0  # Excel处理
- openai >= 1.0.0    # OpenAI API
- pandas >= 2.0.0    # 数据处理
- lark-oapi >= 1.0.0 # 飞书SDK
- flask >= 2.0.0     # Web服务

## 飞书机器人接入 (可选)

### 1. 创建飞书应用
1. 访问 https://open.feishu.cn/app 创建应用
2. 添加机器人能力
3. 获取 App ID 和 App Secret

### 2. 配置回调
1. 在应用权限中开启 `im:message:send_as_bot`
2. 创建事件订阅回调地址 (需要公网访问)
3. 订阅 `im.message.message_v1` 事件

### 3. 启动服务
```bash
# 设置环境变量
set LARK_APP_ID=your-app-id
set LARK_APP_SECRET=your-app-secret
set OPENAI_API_KEY=your-openai-key
set PORT=5000

# 启动飞书机器人
python feishu_bot.py
```

### 4. 使用方式
在飞书群聊中发送命令:
- `直接上传 BOM 文件` - 自动导入并设置上传人为主人
- `/查询 STM32` - 搜索物料
- `/谁有 STM32F103` - 查询物料归属
- `/列表` - 查看所有库存
- `/导出` - 导出库存表

## 使用方法
```bash
# 安装依赖
pip install -r requirements.txt

# 配置API Key
export OPENAI_API_KEY="your-key"

# 运行
python main.py --upload BOM.xlsx
python main.py --query "STM32F103"
python main.py --list
```