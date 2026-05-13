import json
from datetime import datetime
from pathlib import Path
import config
import re
from component_types import get_matching_type_names, KEYWORD_TO_TYPES


class InventoryManager:
    def __init__(self):
        self.inventory_file = config.INVENTORY_FILE
        self.data = self._load_inventory()

    def _load_inventory(self) -> dict:
        if self.inventory_file.exists():
            with open(self.inventory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return self._convert_from_list(data)
                return data
        return {"parts": {}, "bom": []}

    def _convert_from_list(self, items: list) -> dict:
        parts = {}
        bom = []
        for item in items:
            part_num = item.get("料号", "")
            if part_num:
                parts[part_num] = {
                    "name": item.get("名称", ""),
                    "package": item.get("封装", ""),
                    "value": item.get("容值", ""),
                    "manufacturer": item.get("生产商", ""),
                    "supplier": item.get("供应商", ""),
                    "stock": item.get("数量", 0),
                    "owner": item.get("主人", ""),
                    "comments": item.get("备注", ""),
                }
                bom.append({
                    "designator": item.get("designator", ""),
                    "part": part_num,
                })
        return {"parts": parts, "bom": bom}

    def _save_inventory(self):
        with open(self.inventory_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @property
    def parts(self) -> dict:
        return self.data.get("parts", {})

    @property
    def bom(self) -> list:
        return self.data.get("bom", [])

    @property
    def history(self) -> list:
        return self.data.get("history", [])

    def add_items(self, items: list):
        timestamp = datetime.now().isoformat()
        owner = ""
        
        for new_item in items:
            part_num = new_item.get("料号", "")
            owner = new_item.get("主人", "")
            part_info = {
                "name": new_item.get("名称", ""),
                "package": new_item.get("封装", ""),
                "value": new_item.get("容值", ""),
                "manufacturer": new_item.get("生产商", ""),
                "supplier": new_item.get("供应商", ""),
                "stock": new_item.get("数量", 0),
                "owner": new_item.get("主人", ""),
                "comments": new_item.get("备注", ""),
            }
            if part_num in self.parts:
                self.parts[part_num]["stock"] += new_item.get("数量", 0)
                self.parts[part_num]["owner"] = new_item.get("主人", self.parts[part_num]["owner"])
                self.parts[part_num]["upload_time"] = timestamp
            else:
                part_info["upload_time"] = timestamp
                self.parts[part_num] = part_info
        
        if "history" not in self.data:
            self.data["history"] = []
        added_items = {}
        for new_item in items:
            pn = new_item.get("料号", "")
            qty = new_item.get("数量", 0)
            if pn:
                added_items[pn] = added_items.get(pn, 0) + qty
        self.data["history"].append({
            "time": timestamp,
            "owner": owner,
            "count": len(items),
            "added_items": added_items,
        })
        self._save_inventory()

    def delete_upload(self, query: str) -> tuple[bool, str]:
        """Delete an upload by 1-based index or timestamp prefix.
        Returns (success, message)."""
        history = self.data.get("history", [])
        if not history:
            return False, "没有上传历史"
        
        entry = None
        
        # 先尝试按序号匹配
        try:
            index = int(query)
            if 1 <= index <= len(history):
                entry = history[-index]
        except ValueError:
            pass
        
        # 再尝试按时间戳匹配
        if entry is None:
            matches = []
            for i, h in enumerate(reversed(history), 1):
                time_str = h.get("time", "")
                if query in time_str:
                    matches.append((i, h))
            
            if len(matches) == 0:
                return False, f"未找到匹配 '{query}' 的记录"
            elif len(matches) > 1:
                lines = [f"⚠️ 找到 {len(matches)} 条匹配记录，请用序号精确删除：\n"]
                for idx, h in matches:
                    lines.append(f"{idx}. [{h['time'][:19]}] {h['owner']} — {h['count']} 条")
                return False, "\n".join(lines)
            else:
                entry = matches[0][1]
        
        # 兼容旧版(items)和新版(added_items)字段名
        items = entry.get("items") or entry.get("added_items") or {}
        if not items:
            return False, "该记录没有物料数据，无法回滚（旧记录不支持删除）"
        
        removed_count = 0
        for part_num, qty in items.items():
            if part_num in self.parts:
                self.parts[part_num]["stock"] -= qty
                if self.parts[part_num]["stock"] <= 0:
                    del self.parts[part_num]
                removed_count += 1
        
        history.remove(entry)
        self._save_inventory()
        return True, f"✅ 已回滚 {entry['owner']} 的上传（{entry['time']}），共 {removed_count} 条物料"

    def who_has(self, part_number: str) -> list:
        """查询物料归属信息"""
        if not part_number:
            return []
        item = self.parts.get(part_number)
        if not item:
            # 尝试模糊匹配料号
            for pn, it in self.parts.items():
                if part_number.lower() in pn.lower():
                    return [self._to_display_item(pn, it)]
            return []
        return [self._to_display_item(part_number, item)]

    def query(self, keyword: str) -> list:
        keyword = keyword.lower()
        results = []
        for part_num, item in self.parts.items():
            if (
                keyword in item.get("name", "").lower()
                or keyword in part_num.lower()
                or keyword in item.get("manufacturer", "").lower()
                or keyword in item.get("supplier", "").lower()
                or keyword in item.get("comments", "").lower()
                or keyword in item.get("package", "").lower()
                or keyword in item.get("value", "").lower()
            ):
                results.append(self._to_display_item(part_num, item))
        return results

    def smart_query(self, text: str) -> list:
        """智能查询：类型 + 容值 + 封装 三层精确过滤"""
        text = text.lower().strip()

        # 连接器特殊处理
        if self._is_connector_query(text):
            return self._query_connector(text)

        # 提取约束条件
        target_types = self._extract_types(text)
        target_value = self._extract_value(text)
        target_packages = self._extract_packages(text)

        has_constraints = bool(target_types or target_value or target_packages)

        # 无约束时退化为普通查询
        if not has_constraints:
            return self.query(text)

        # 三层过滤
        results = []
        for part_num, item in self.parts.items():
            # 类型过滤
            if target_types and not self._type_matches(target_types, item):
                continue

            # 容值过滤
            if target_value and not self._value_matches(target_value, item.get("value", "")):
                continue

            # 封装过滤
            if target_packages and not self._package_matches(target_packages, item.get("package", "")):
                continue

            results.append(self._to_display_item(part_num, item))

        return results

    # ---------- 智能查询辅助方法 ----------

    def _is_connector_query(self, text: str) -> bool:
        connector_keywords = ["排针", "header", "座", "connector", "接插件", "连接件", "针座", "wafer"]
        return any(kw in text for kw in connector_keywords)

    def _query_connector(self, text: str) -> list:
        """连接器专用查询"""
        results = []

        pin_match = re.search(r"(\d+)\s*p", text)
        if pin_match:
            pin_count = pin_match.group(1)
            for part_num, item in self.parts.items():
                if item.get("name", "") not in ["连接器", "排针"]:
                    continue
                package = item.get("package", "").lower()
                if f"{pin_count}p" in package:
                    results.append(self._to_display_item(part_num, item))
        else:
            for part_num, item in self.parts.items():
                if item.get("name", "") not in ["连接器", "排针"]:
                    continue
                package = item.get("package", "").lower()
                if "conn" in package or "wafer" in package or "header" in package:
                    results.append(self._to_display_item(part_num, item))

        return results

    def _extract_types(self, text: str) -> list[str] | None:
        """从查询文本中提取组件类型"""
        found_types = []
        for keyword, types in KEYWORD_TO_TYPES.items():
            if keyword in text:
                found_types.extend(types)
        return list(set(found_types)) if found_types else None

    def _type_matches(self, target_types: list[str], item: dict) -> bool:
        return item.get("name", "") in target_types

    def _extract_value(self, text: str) -> dict | None:
        """从容值/阻值查询中提取标准化值"""
        # 电阻模式
        resistor_patterns = [
            (r'(\d+(?:\.\d+)?)\s*(k|m)?\s*[ΩO欧](?:姆|hm)?', 'resistor'),
            (r'(\d+(?:\.\d+)?)\s*(k|m)?\s*欧姆', 'resistor'),
            (r'(\d+(?:\.\d+)?)\s*(k|m)?\s*ohm', 'resistor'),
        ]

        for pattern, vtype in resistor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = match.group(1)
                multiplier = match.group(2) if match.group(2) else ''
                return {'type': vtype, 'raw': f"{num}{multiplier}Ω"}

        # 电容模式
        capacitor_patterns = [
            (r'(\d+(?:\.\d+)?)\s*(u|μ|p|n)?\s*f', 'capacitor'),
        ]

        for pattern, vtype in capacitor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = match.group(1)
                multiplier = match.group(2) if match.group(2) else ''
                return {'type': vtype, 'raw': f"{num}{multiplier}F"}

        # 电感模式
        inductor_patterns = [
            (r'(\d+(?:\.\d+)?)\s*(u|μ|m)?\s*h', 'inductor'),
        ]

        for pattern, vtype in inductor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                num = match.group(1)
                multiplier = match.group(2) if match.group(2) else ''
                return {'type': vtype, 'raw': f"{num}{multiplier}H"}

        return None

    def _normalize_value(self, value_str: str) -> tuple[float, str] | None:
        """将容值字符串解析为 (数值, 单位)"""
        value_str = value_str.lower().strip()

        # 电阻
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(k|m)?\s*[ΩO欧](?:姆|hm)?$', value_str)
        if match:
            num = float(match.group(1))
            multiplier = match.group(2)
            if multiplier == 'k':
                num *= 1000
            elif multiplier == 'm':
                num *= 1000000
            return (num, 'Ω')

        # 电容
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(u|μ|p|n)?\s*f$', value_str)
        if match:
            num = float(match.group(1))
            multiplier = match.group(2)
            if multiplier == 'p':
                pass
            elif multiplier in ('n', 'μ'):
                num *= 1000
            elif multiplier == 'u':
                num *= 1000000
            return (num, 'F')

        # 电感
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(u|μ|m)?\s*h$', value_str)
        if match:
            num = float(match.group(1))
            multiplier = match.group(2)
            if multiplier in ('u', 'μ'):
                num *= 0.001
            return (num, 'H')

        return None

    def _value_matches(self, target: dict, item_value: str) -> bool:
        """比较查询容值和库存容值是否匹配"""
        target_normalized = self._normalize_value(target['raw'])
        item_normalized = self._normalize_value(item_value)

        if not target_normalized or not item_normalized:
            # 无法标准化时退化为子串匹配
            return target['raw'].lower() in item_value.lower()

        # 类型和单位都要匹配
        if target_normalized[1] != item_normalized[1]:
            return False

        # 数值允许小误差
        return abs(target_normalized[0] - item_normalized[0]) < 0.001

    def _extract_packages(self, text: str) -> list[str] | None:
        package_keywords = ["0402", "0603", "0805", "1206", "1210", "2010", "2512"]
        found = [p for p in package_keywords if p in text]
        return found if found else None

    def _package_matches(self, targets: list[str], package: str) -> bool:
        package = package.lower()
        return any(t.lower() in package for t in targets)

    def _to_display_item(self, part_num: str, item: dict) -> dict:
        return {
            "name": item.get("name", ""),
            "part_number": part_num,
            "quantity": item.get("stock", 0),
            "数量": item.get("stock", 0),
            "manufacturer": item.get("manufacturer", ""),
            "supplier": item.get("supplier", ""),
            "owner": item.get("owner", ""),
            "封装": item.get("package", ""),
            "容值": item.get("value", ""),
            "上传人": item.get("owner", ""),
        }

    def list_all(self) -> list:
        results = []
        for part_num, item in self.parts.items():
            results.append(self._to_display_item(part_num, item))
        return results

    def export(self, format: str = "excel") -> str:
        from datetime import datetime
        from bom_processor import BOMProcessor

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format == "excel":
            output = config.DATA_DIR / f"inventory_{timestamp}.xlsx"
            BOMProcessor.export_to_excel(self.list_all(), str(output))
        else:
            output = config.DATA_DIR / f"inventory_{timestamp}.csv"
            BOMProcessor.export_to_csv(self.list_all(), str(output))
        return str(output)
