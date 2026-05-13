from pathlib import Path
from typing import TypedDict
from inventory import InventoryManager
from bom_processor import BOMProcessor


class MatchResult(TypedDict):
    total_count: int
    duplicate_count: int
    duplicate_items: list[dict]
    remaining_items: list[dict]
    duplicate_summary: str


class BOMMatcher:
    @staticmethod
    def compare_with_inventory(items: list[dict]) -> MatchResult:
        """
        对比 BOM 物料和库存，找出重复项。

        匹配逻辑（按优先级）：
        1. 料号完全匹配（Manufacturer Part）→ 最准确
        2. 名称+封装+容值 三者同时匹配 → 近似匹配（仅对料号为空的物料）
        3. 都不匹配 → 新物料
        """
        inv = InventoryManager()
        parts = inv.parts  # dict keyed by 料号

        total_count = len(items)
        matched_indices: set[int] = set()
        duplicate_items: list[dict] = []

        # --- Step 1: 料号精确匹配（case-insensitive）---
        for i, item in enumerate(items):
            part_num = item.get("料号", "").strip()
            if not part_num:
                continue

            for inv_part_num, inv_item in parts.items():
                if part_num.lower() == inv_part_num.lower():
                    matched_indices.add(i)
                    duplicate_items.append({
                        "name": item.get("名称", ""),
                        "part_number": part_num,
                        "package": item.get("封装", ""),
                        "value": item.get("容值", ""),
                        "quantity": item.get("数量", 0),
                        "inventory_quantity": inv_item.get("stock", 0),
                        "manufacturer": item.get("生产商", ""),
                    })
                    break

        # --- Step 2: 名称+封装+容值 近似匹配（仅对料号为空的物料）---
        for i, item in enumerate(items):
            if i in matched_indices:
                continue

            part_num = item.get("料号", "").strip()
            if part_num:
                # 有料号但没在 Step 1 匹配上 → 新物料，跳过近似匹配
                continue

            bom_name = item.get("名称", "").strip().lower()
            bom_pkg = item.get("封装", "").strip().lower()
            bom_val = item.get("容值", "").strip().lower()

            # 三个字段都为空时无法近似匹配
            if not bom_name and not bom_pkg and not bom_val:
                continue

            for inv_part_num, inv_item in parts.items():
                inv_name = inv_item.get("name", "").strip().lower()
                inv_pkg = inv_item.get("package", "").strip().lower()
                inv_val = inv_item.get("value", "").strip().lower()

                if bom_name == inv_name and bom_pkg == inv_pkg and bom_val == inv_val:
                    matched_indices.add(i)
                    duplicate_items.append({
                        "name": item.get("名称", ""),
                        "part_number": inv_part_num,
                        "package": item.get("封装", ""),
                        "value": item.get("容值", ""),
                        "quantity": item.get("数量", 0),
                        "inventory_quantity": inv_item.get("stock", 0),
                        "manufacturer": item.get("生产商", ""),
                    })
                    break

        # --- Step 3: 剩余未匹配物料 ---
        remaining_items = [
            item for i, item in enumerate(items) if i not in matched_indices
        ]

        duplicate_count = len(duplicate_items)
        duplicate_summary = BOMMatcher.format_duplicate_list(duplicate_items)

        return {
            "total_count": total_count,
            "duplicate_count": duplicate_count,
            "duplicate_items": duplicate_items,
            "remaining_items": remaining_items,
            "duplicate_summary": duplicate_summary,
        }

    @staticmethod
    def generate_reduced_bom(items: list[dict], output_path: str) -> str:
        """
        生成精简后的 BOM Excel 文件。
        返回生成的文件路径。
        """
        BOMProcessor.export_to_excel(items, output_path)
        return output_path

    @staticmethod
    def format_duplicate_list(duplicate_items: list[dict], max_display: int = 10) -> str:
        """
        格式化重复项列表为消息文本。
        超过 max_display 条时显示摘要。
        """
        if not duplicate_items:
            return "无重复物料"

        lines = []
        for item in duplicate_items[:max_display]:
            name = item.get("name", "")
            value = item.get("value", "")
            pkg = item.get("package", "")
            part_num = item.get("part_number", "")
            qty = item.get("quantity", 0)
            inv_qty = item.get("inventory_quantity", 0)

            # 电容 47uF C0603 (GRM188R60J476ME15D) ×5 — 库存: 4
            parts_display = [name]
            if value:
                parts_display.append(value)
            if pkg:
                parts_display.append(pkg)
            if part_num:
                parts_display.append(f"({part_num})")

            line = " ".join(parts_display)
            line += f" ×{qty} — 库存: {inv_qty}"
            lines.append(line)

        remaining = len(duplicate_items) - max_display
        if remaining > 0:
            lines.append(f"... (还有 {remaining} 条)")

        return "\n".join(lines)
