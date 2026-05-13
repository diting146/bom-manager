# 测试飞书文件上传功能

1. 确保已安装依赖:
```bash
pip install -r requirements.txt
```

2. 配置飞书开放平台权限:
- 需要添加以下权限:
  - drive:drive:readonly (用于下载文件)
  - contact:user.base:readonly (用于获取用户信息)

3. 测试步骤:
- 在飞书中给机器人发送一个 BOM 文件 (Excel 或 CSV 格式)
- 机器人应该:
  - 获取上传者的名字
  - 下载并解析文件
  - 为所有物料设置"主人"字段为上传者名字
  - 将物料添加到总库存
  - 返回成功消息

4. 预期输出:
```
✅ BOM文件上传成功！
上传人: 张三
新增物料: 15 条
```

5. 验证:
- 检查 data/inventory.json 文件
- 确认物料已添加
- 确认"主人"字段已正确设置
