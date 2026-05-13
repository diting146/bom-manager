"""飞书电子表格云同步模块

将 BOM 库存数据同步到飞书电子表格，作为共享云总表。
"""
import json
import time
from datetime import datetime
from pathlib import Path

import requests

import config


class CloudSheetManager:
    """管理飞书电子表格的创建、读取和写入"""

    TABLE_FIELDS = ["名称", "料号", "封装", "容值", "数量", "生产商", "供应商", "主人", "上传时间"]

    def __init__(self):
        self.config_file = config.DATA_DIR / "cloud_sheet.json"
        self.app_id = config.LARK_APP_ID
        self.app_secret = config.LARK_APP_SECRET
        self._access_token = None
        self._token_expire_time = 0
        self._sheet_cfg = self._load_config()

    def _load_config(self) -> dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._sheet_cfg, f, ensure_ascii=False, indent=2)

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expire_time - 60:
            return self._access_token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        try:
            resp = requests.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=10)
            data = resp.json()
        except Exception as e:
            raise Exception(f"请求 access_token 失败: {e}")

        if data.get("code") != 0:
            raise Exception(f"获取 access_token 失败: {data}")

        self._access_token = data["tenant_access_token"]
        self._token_expire_time = now + data.get("expire", 7200)
        return self._access_token

    def _api_call(self, method: str, url: str, **kwargs) -> dict:
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
            data = resp.json()
        except Exception as e:
            print(f"[CloudSheet] API 请求异常: {e}")
            return {"code": -1, "msg": str(e)}

        if data.get("code") != 0:
            print(f"[CloudSheet] API 错误: {data}")
        return data

    def _get_sheet_id(self, spreadsheet_token: str) -> str:
        """获取第一个 sheet 的 ID"""
        url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query"
        data = self._api_call("GET", url)
        sheets = data.get("data", {}).get("sheets", [])
        if not sheets:
            raise Exception("无法获取 sheet 信息")
        return sheets[0]["sheet_id"]

    def _col_letter(self, n: int) -> str:
        """数字列号转字母（1 -> A, 27 -> AA）"""
        result = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            result = chr(65 + r) + result
        return result

    # ---------- 公开接口 ----------

    def create_spreadsheet(self, title: str = "BOM库存总表") -> str:
        """创建新的电子表格，返回 spreadsheet_token"""
        url = "https://open.feishu.cn/open-apis/sheets/v3/spreadsheets"
        body = {"title": title}
        data = self._api_call("POST", url, json=body)

        if data.get("code") != 0:
            raise Exception(f"创建表格失败: {data}")

        token = data["data"]["spreadsheet"]["spreadsheet_token"]
        self._sheet_cfg["spreadsheet_token"] = token
        self._save_config()

        # 尝试设置租户内可读权限（静默失败）
        self._set_public_permission(token)

        return token

    def _set_public_permission(self, token: str):
        """设置表格为租户内成员可查看"""
        url = "https://open.feishu.cn/open-apis/drive/v1/permissions/{token}/members"
        body = {
            "member_type": "tenant",
            "member_id": "0",
            "perm": "view",
        }
        # 使用路径参数
        url = url.format(token=token)
        data = self._api_call("POST", url, json=body)
        if data.get("code") == 0:
            print("[CloudSheet] 已设置租户内可读权限")
        else:
            print(f"[CloudSheet] 设置权限失败（可手动分享）: {data.get('msg', '')}")

    def ensure_spreadsheet(self) -> str:
        """确保表格已创建，返回 token"""
        token = self._sheet_cfg.get("spreadsheet_token")
        if token:
            return token
        return self.create_spreadsheet()

    def get_link(self) -> str | None:
        """获取表格分享链接"""
        token = self._sheet_cfg.get("spreadsheet_token")
        if not token:
            return None
        return f"https://open.feishu.cn/sheets/{token}"

    def write_values(self, values: list[list]) -> bool:
        """全量覆盖写入数据"""
        token = self.ensure_spreadsheet()
        sheet_id = self._get_sheet_id(token)

        rows = len(values)
        cols = len(values[0]) if values else 0
        end_col = self._col_letter(cols)
        range_str = f"{sheet_id}!A1:{end_col}{rows}"

        # 先清空旧数据（写入空值覆盖更大范围）
        if rows > 1:
            clear_range = f"{sheet_id}!A1:{end_col}{max(rows * 2, 100)}"
            clear_url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{token}/values"
            self._api_call("PUT", clear_url, json={"valueRange": {"range": clear_range, "values": []}})

        # 写入新数据
        url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{token}/values"
        body = {"valueRange": {"range": range_str, "values": values}}
        data = self._api_call("PUT", url, json=body)

        return data.get("code") == 0

    def sync_inventory(self) -> tuple[bool, str | None]:
        """
        从本地 inventory.json 读取全量数据，覆盖写入云表格。
        返回 (success, link_or_error)
        """
        try:
            from inventory import InventoryManager

            inv = InventoryManager()
            parts = inv.parts

            values = [self.TABLE_FIELDS]
            for part_num, item in parts.items():
                values.append(
                    [
                        item.get("name", ""),
                        part_num,
                        item.get("package", ""),
                        item.get("value", ""),
                        str(item.get("stock", 0)),
                        item.get("manufacturer", ""),
                        item.get("supplier", ""),
                        item.get("owner", ""),
                        item.get("upload_time", ""),
                    ]
                )

            success = self.write_values(values)
            link = self.get_link()
            return success, link if success else "写入失败"
        except Exception as e:
            print(f"[CloudSheet] 同步失败: {e}")
            return False, str(e)

    def get_or_create(self) -> str:
        """获取表格链接，不存在则创建"""
        link = self.get_link()
        if link:
            return link
        self.create_spreadsheet()
        return self.get_link()
