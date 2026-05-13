import json
from openai import OpenAI
import config


class AIProcessor:
    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError("请设置 OPENAI_API_KEY 环境变量")
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY, base_url="https://openrouter.ai/api/v1"
        )

    def query_inventory(self, query: str, inventory: list) -> list:
        if not inventory:
            return []

        prompt = self._build_query_prompt(query, inventory)

        try:
            response = self.client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个物料查询助手。根据用户的自然语言查询，从库存中找出匹配的物料。
返回JSON数组，每个元素包含匹配物料的信息。
如果没有匹配，返回空数组[]。
只返回JSON数组，不要其他内容。""",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            result = response.choices[0].message.content.strip()
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]

            matched = json.loads(result.strip())
            return matched if isinstance(matched, list) else []
        except Exception as e:
            print(f"AI查询失败: {e}")
            return []

    def _build_query_prompt(self, query: str, inventory: list) -> str:
        inventory_summary = []
        for item in inventory[:100]:
            inventory_summary.append(
                {
                    "名称": item.get("name", ""),
                    "封装": item.get("封装", ""),
                    "容值": item.get("容值", ""),
                    "料号": item.get("part_number", ""),
                    "数量": item.get("数量", 0),
                    "生产商": item.get("manufacturer", ""),
                    "上传人": item.get("上传人", ""),
                }
            )

        prompt = f"""用户查询: {query}

库存物料:
{json.dumps(inventory_summary, ensure_ascii=False, indent=2)}

请找出所有匹配的物料，返回JSON数组。每个物料需要包含: 名称, 封装, 容值, 数量, 料号, 生产商, 上传人。
只返回JSON数组，不要其他内容。"""
        return prompt

    def organize_items(self, items: list) -> list:
        if not items:
            return []

        prompt = self._build_prompt(items)
        response = self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个BOM整理助手。请将物料标准化，去重，合并相同物料。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        try:
            result = response.choices[0].message.content
            organized = json.loads(result)
            return organized if isinstance(organized, list) else items
        except (json.JSONDecodeError, AttributeError):
            return items

    def _build_prompt(self, items: list) -> str:
        prompt = "请将以下BOM物料整理成标准化JSON数组。每个物料包含：name(名称), part_number(料号), quantity(数量), owner(负责人), location(位置), category(分类), description(描述)。相同物料请合并数量。\n\n"
        prompt += "输入物料：\n"
        for item in items:
            prompt += f"- {item}\n"
        prompt += "\n请直接返回JSON数组，不要其他内容。"
        return prompt

