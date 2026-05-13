import sys

sys.path.insert(0, "F:/BOM")
from ai_processor import AIProcessor
from inventory import InventoryManager

ai = AIProcessor()
inv = InventoryManager()

queries = [
    "我要一个0805的10欧电阻",
    "查询100Ω的电阻",
    "我要找电容",
    "给我一个18MHz的晶振",
]

for q in queries:
    results = ai.query_inventory(q, inv.list_all())
    print(f"\n=== 查询: {q} ===")
    print(f"找到 {len(results)} 条")
    for r in results[:3]:
        print(
            f"  {r.get('名称', '')} {r.get('封装', '')} {r.get('容值', '')} {r.get('料号', '')}"
        )
