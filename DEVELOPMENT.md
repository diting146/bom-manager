# BOM 飞书机器人开发记录

## 快速启动

```bash
cd F:\BOM
py feishu_bot.py
```

## 服务地址

- ngrok: https://stank-handyman-favorite.ngrok-free.dev/webhook
- 本地: http://127.0.0.1:5000

## 启动顺序

1. 先启动 ngrok（如果断了）:
```bash
.\ngrok.exe http 5000
```

2. 再启动飞书机器人:
```bash
py feishu_bot.py
```

## 数据文件

- 库存数据: `F:\BOM\data\inventory.json`
- BOM模板: `F:\BOM\BOM_原件参考下载.xlsx`

## 重新导入数据

```bash
Remove-Item F:\BOM\data\inventory.json -Force
py -c "from pathlib import Path; import os; os.chdir('F:/BOM'); f=list(Path('.').glob('*.xlsx'))[0]; from bom_processor import BOMProcessor; from inventory import InventoryManager; items=BOMProcessor.read_file(f.name); InventoryManager().add_items(items); print(f'OK {len(items)} items')"
```

## 飞书开放平台配置

- App ID: cli_a963bf199a389cef
- 事件订阅URL: https://stank-handyman-favorite.ngrok-free.dev/webhook
- 订阅事件: im.message.receive_v1
- 权限: 
  - im:message.p2p_msg:readonly
  - im:message:send_as_bot
  - im:message
  - drive:drive:readonly (下载文件)
  - contact:user.base:readonly (获取用户信息)

## 已完成功能

- [x] 飞书机器人接收消息
- [x] 发送回复
- [x] 解析飞书v2.0事件格式
- [x] lark-oapi 1.5.5 SDK 发送消息

## 待完成功能

- [ ] 自然语言查询（查询 100Ω 0402 电阻）
- [ ] 数据字段优化（名称、封装、容值、数量、料号、生产商、主人）
- [ ] 主人字段留空

## 当前数据结构

```json
{
    "名称": "电容",
    "封装": "C0603",
    "容值": "47uF",
    "数量": 1,
    "料号": "GRM188R60J476ME15D",
    "生产商": "muRata(村田)",
    "供应商": "LCSC",
    "备注": "47uF",
    "主人": "",
    "designator": "C1"
}
```

## 常用命令

- 列表 - 查看所有库存
- 查询 [关键词] - 搜索物料
- 帮助 - 显示帮助