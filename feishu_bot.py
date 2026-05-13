import os
import json
import tempfile
import requests
import hmac
import hashlib
import base64
import config
from bom_processor import BOMProcessor
from ai_processor import AIProcessor
from inventory import InventoryManager
from cloud_sheet import CloudSheetManager
from flask import Flask, request, jsonify
from lark_oapi import Client, LogLevel
import re
from component_types import KEYWORD_TYPE_MAP
from datetime import datetime
from conversation import (
    ConversationManager, MODE_ADD, MODE_EXTRACT,
    STATE_UPLOADED, STATE_SELECTING, STATE_CONFIRMING, STATE_MANUAL_PACKAGE, STATE_MANUAL_INPUT,
    STATE_COMPLETED, STATE_EXPIRED,
    MODE_SELECT_MSG, DUPLICATE_SUMMARY_MSG, MANUAL_INPUT_HELP, MANUAL_PACKAGE_PROMPT,
)
from bom_matcher import BOMMatcher
from pathlib import Path


APP_ID = config.LARK_APP_ID
APP_SECRET = config.LARK_APP_SECRET

app = Flask(__name__)
client = (
    Client.builder()
    .app_id(APP_ID)
    .app_secret(APP_SECRET)
    .log_level(LogLevel.INFO)
    .build()
)

inventory = InventoryManager()
ai_processor = None
try:
    ai_processor = AIProcessor()
except Exception as e:
    print(f"AI处理器初始化失败: {e}")

cloud_sheet = None
try:
    cloud_sheet = CloudSheetManager()
    print("[CloudSheet] 初始化成功")
except Exception as e:
    print(f"[CloudSheet] 初始化失败: {e}")

processed_messages = set()

conversation_mgr = ConversationManager()


def load_authorized_users() -> list[str]:
    """读取可删除库存的用户白名单"""
    auth_file = config.AUTHORIZED_USERS_FILE
    if auth_file.exists():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def is_authorized(user_id: str) -> bool:
    """检查用户是否有删除权限"""
    user_name = get_user_name(user_id)
    authorized = load_authorized_users()
    return user_name in authorized

def load_admins() -> list[str]:
    """读取超级管理员列表"""
    admin_file = config.BASE_DIR / "data" / "admins.json"
    if admin_file.exists():
        try:
            with open(admin_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def is_super_admin(user_id: str) -> bool:
    """检查用户是否是超级管理员"""
    user_name = get_user_name(user_id)
    admins = load_admins()
    return user_name in admins

def do_authorize(target_name: str, admin_id: str) -> str:
    """授权用户删除权限"""
    if not is_super_admin(admin_id):
        return "❌ 只有超级管理员可以授权他人"
    
    authorized = load_authorized_users()
    if target_name in authorized:
        return f"⚠️ {target_name} 已经有权限了"
    
    authorized.append(target_name)
    try:
        with open(config.AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(authorized, f, ensure_ascii=False, indent=2)
        return f"✅ 已授权 {target_name} 删除权限"
    except Exception as e:
        return f"❌ 授权失败: {e}"

def do_revoke(target_name: str, admin_id: str) -> str:
    """取消用户删除权限"""
    if not is_super_admin(admin_id):
        return "❌ 只有超级管理员可以取消授权"
    
    authorized = load_authorized_users()
    if target_name not in authorized:
        return f"⚠️ {target_name} 没有权限"
    
    authorized.remove(target_name)
    try:
        with open(config.AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(authorized, f, ensure_ascii=False, indent=2)
        return f"✅ 已取消 {target_name} 的删除权限"
    except Exception as e:
        return f"❌ 取消授权失败: {e}"

def parse_manual_item(text: str, batch_package: str = None) -> dict | None:
    """解析手动录入文本为物料字典。
    
    batch_package 为 None 时，格式：容值, 封装
    batch_package 非空时，格式：容值（封装自动填充）
    """
    import re
    if batch_package:
        # 批量模式：只输入容值
        value = text.strip()
        if not value:
            return None
        package = batch_package
        qty = "1"
    else:
        # 普通模式：容值, 封装 [, 数量]
        parts = [p.strip() for p in text.split(",", 2)]
        if len(parts) < 2 or not parts[1]:
            return None
        value = parts[0]
        package = parts[1]
        qty = parts[2] if len(parts) > 2 else "1"
    
    try:
        qty = int(qty)
    except ValueError:
        qty = 1

    # 自动推断组件类型
    value_lower = value.lower()
    if re.search(r'[ΩωO欧]', value_lower) or re.search(r'ohm', value_lower):
        name = "电阻"
    elif re.search(r'[Ff]$', value_lower) or re.search(r'[ufnpμ]f', value_lower):
        name = "电容"
    elif re.search(r'[Hh]$', value_lower) or re.search(r'[uμ]h|mh', value_lower):
        name = "电感"
    else:
        name = "其他"

    # 生成临时料号（用于回滚）
    part_number = f"{name}_{value}_{package}".replace(" ", "_")

    return {
        "名称": name,
        "料号": part_number,
        "封装": package,
        "容值": value,
        "数量": qty,
        "生产商": "",
        "供应商": "",
        "备注": "",
        "主人": "",
        "designator": "",
    }

def do_show_history() -> str:
    """显示上传历史"""
    history = inventory.history
    if not history:
        return "暂无上传历史"
    lines = [f"📜 上传历史（共 {len(history)} 条）:\n"]
    for i, entry in enumerate(reversed(history), 1):
        time_str = entry.get("time", "?")[:19]
        owner = entry.get("owner", "?")
        count = entry.get("count", 0)
        lines.append(f"{i}. [{time_str}] {owner} — {count} 条")
    return "\n".join(lines)

def do_delete_upload(query: str, user_id: str) -> str:
    """删除上传记录（支持序号或时间戳）"""
    if not is_authorized(user_id):
        return "❌ 你没有删除权限（请联系管理员添加到白名单）"
    success, msg = inventory.delete_upload(query)
    if success and cloud_sheet:
        try:
            cloud_sheet.sync_inventory()
        except Exception as e:
            print(f"[CloudSheet] 同步异常: {e}")
    return msg


def handle_conversation_response(text: str, user_id: str) -> str | None:
    session = conversation_mgr.get(user_id)
    if not session:
        return None
    
    text = text.strip().lower()
    
    if session.state == STATE_SELECTING:
        if text in ["1", "加入", "加入库存", "add"]:
            if conversation_mgr.select_mode(user_id, MODE_ADD):
                for item in session.uploaded_items:
                    item["主人"] = get_user_name(user_id)
                inventory.add_items(session.uploaded_items)
                
                sheet_msg = ""
                if cloud_sheet:
                    try:
                        success, link = cloud_sheet.sync_inventory()
                        if success:
                            sheet_msg = f"\n📊 已同步到云表格: {link}"
                    except Exception as e:
                        print(f"[CloudSheet] 同步异常: {e}")
                
                return f"✅ 已加入库存！新增 {session.uploaded_count} 条物料{sheet_msg}"
            return "❌ 操作失败"
            
        elif text in ["2", "摘取", "摘取物料", "extract"]:
            if conversation_mgr.select_mode(user_id, MODE_EXTRACT):
                results = BOMMatcher.compare_with_inventory(session.uploaded_items)
                conversation_mgr.set_matched_results(user_id, results)
                
                return DUPLICATE_SUMMARY_MSG.format(
                    duplicate_count=results["duplicate_count"],
                    total_count=results["total_count"],
                    duplicate_list=results["duplicate_summary"],
                    remaining_count=len(results["remaining_items"]),
                )
            return "❌ 操作失败"
        else:
            return "❓ 请选择：1️⃣ 加入库存 或 2️⃣ 摘取物料"
    
    elif session.state == STATE_CONFIRMING:
        if text in ["1", "移除", "移除重复项", "remove"]:
            results = session.matched_results
            if not results:
                return "❌ 对比结果已过期"
            
            remaining = results["remaining_items"]
            if not remaining:
                return "ℹ️ 所有物料都已存在于库存中，无需生成新 BOM"
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(config.DATA_DIR / f"reduced_bom_{timestamp}.xlsx")
            BOMMatcher.generate_reduced_bom(remaining, output_path)
            
            # 尝试上传并发送文件
            sent_msg = ""
            try:
                file_key = upload_feishu_file(output_path)
                if file_key and send_file_message(file_key, session.chat_id):
                    sent_msg = "\n📎 文件已发送到聊天中"
                else:
                    sent_msg = f"\n文件已保存到: {output_path}"
            except Exception as e:
                print(f"[SendFile] 发送异常: {e}")
                sent_msg = f"\n文件已保存到: {output_path}"
            
            conversation_mgr.complete(user_id)
            
            return f"✅ 已生成精简 BOM：{len(remaining)} 条新物料（已移除 {results['duplicate_count']} 条重复）{sent_msg}"
            
        elif text in ["2", "保留", "保留所有", "keep"]:
            conversation_mgr.complete(user_id)
            return "ℹ️ 已保留所有物料，不做处理"
        else:
            return "❓ 请选择：1️⃣ 移除重复项 或 2️⃣ 保留所有"
    
    elif session.state == STATE_MANUAL_PACKAGE:
        # 取第一个词判断，避免"取消 录入"被当作封装
        first_word = text.strip().split()[0].lower() if text.strip().split() else ""
        if first_word in ["取消", "cancel", "放弃"]:
            conversation_mgr.complete(user_id)
            return "ℹ️ 已放弃本次录入"
        session.batch_package = text.strip()
        conversation_mgr.update_state(user_id, STATE_MANUAL_INPUT)
        return f"✅ 已设置封装：{session.batch_package}\n\n现在逐条输入容值即可，发送'完成'结束录入"

    elif session.state == STATE_MANUAL_INPUT:
        # 取第一个词判断，避免"完成 历史"被当作容值
        first_word = text.strip().split()[0].lower() if text.strip().split() else ""
        if first_word in ["完成", "done", "保存"]:
            items = session.uploaded_items
            if not items:
                return "⚠️ 没有录入任何物料"
            for item in items:
                item["主人"] = get_user_name(user_id)
            inventory.add_items(items)
            sheet_msg = ""
            if cloud_sheet:
                try:
                    success, link = cloud_sheet.sync_inventory()
                    if success:
                        sheet_msg = f"\n📊 已同步到云表格: {link}"
                except Exception as e:
                    print(f"[CloudSheet] 同步异常: {e}")
            conversation_mgr.complete(user_id)
            return f"✅ 录入完成！共 {len(items)} 条物料已加入库存{sheet_msg}"
        elif first_word in ["查询", "历史", "删除", "录入", "库存", "帮助", "列表",
                            "query", "history", "delete", "list", "help",
                            "search", "who", "谁有", "归属", "导出", "export",
                            "授权", "取消授权", "authorize", "revoke"]:
            return '⚠️ 当前在录入模式，请先发送 [完成] 结束录入，再使用其他命令'
        elif first_word in ["取消", "cancel", "放弃"]:
            conversation_mgr.complete(user_id)
            return "ℹ️ 已放弃本次录入"
        else:
            item = parse_manual_item(text, batch_package=session.batch_package)
            if item is None:
                if session.batch_package:
                    hint = f"（封装：{session.batch_package}）"
                else:
                    hint = "（如 10kΩ, 0402）"
                return f"❌ 格式错误，请按：容值 {hint}"
            session.uploaded_items.append(item)
            count = len(session.uploaded_items)
            pkg_hint = f" {session.batch_package}" if session.batch_package else ""
            return f"✅ 已记录第 {count} 条：{item['名称']} {item['容值']}{pkg_hint}  ×{item['数量']}\n继续输入下一条，或发送'完成'结束"

    return None


def handle_command(text: str, user_id: str = "") -> str:
    if user_id:
        conv_reply = handle_conversation_response(text, user_id)
        if conv_reply is not None:
            return conv_reply
    
    parts = text.strip().split()
    if not parts:
        return "请输入命令"

    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ["query", "查询", "搜索"]:
        if not args:
            return "请输入查询关键词\n用法: query [关键词]"
        keyword = " ".join(args)
        return do_query(keyword)

    elif cmd in ["who", "谁有", "归属"]:
        if not args:
            return "请输入物料料号\n用法: who [料号]"
        part_number = " ".join(args)
        results = inventory.who_has(part_number)
        return format_who_has(results, part_number)

    elif cmd in ["list", "列表", "库存"]:
        items = inventory.list_all()
        return format_list(items)

    elif cmd in ["help", "帮助", "?"]:
        return get_help()

    elif cmd in ["export", "导出"]:
        output = inventory.export("csv")
        return f"库存已导出: {output}"

    elif cmd in ["链接", "云表格", "sheet"]:
        return do_get_sheet_link()

    elif cmd in ["同步", "sync"]:
        return do_sync_sheet()

    elif cmd in ["录入", "新增", "手动录入"]:
        session = conversation_mgr.get(user_id)
        if session and session.state not in (STATE_COMPLETED, STATE_EXPIRED):
            return "⚠️ 你有一个未完成的会话，请先完成或取消"
        conversation_mgr.create(user_id, user_id, [])
        conversation_mgr.update_state(user_id, STATE_MANUAL_PACKAGE)
        return MANUAL_PACKAGE_PROMPT

    elif cmd in ["历史", "history"]:
        return do_show_history()

    elif re.match(r'^(删除|delete)', cmd, re.I):
        # 支持 "删除 1"、"删除 2026-05-12"、"删除<1>"、"删除[2026-05-12]" 等格式
        match = re.search(r'^(?:删除|delete)\s*(.*)', text, re.I)
        if match and match.group(1).strip():
            query = match.group(1).strip()
            # 去掉 <>〈〉[]（） 等括号
            query = re.sub(r'^[\[<〈（\(]\s*', '', query)
            query = re.sub(r'\s*[\]>〉）\)]$', '', query)
            if query:
                return do_delete_upload(query, user_id)
        return "用法：删除 <序号> 或 删除 <时间戳>（如 2026-05-12）"

    elif re.match(r'^(授权|authorize)', cmd, re.I):
        # 支持 "授权 用户名"、"授权用户名" 等格式
        match = re.search(r'^(?:授权|authorize)\s*(.*)', text, re.I)
        if match and match.group(1).strip():
            return do_authorize(match.group(1).strip(), user_id)
        return "用法：授权 <用户名>"

    elif re.match(r'^(取消授权|revoke)', cmd, re.I):
        # 支持 "取消授权 用户名"、"取消授权用户名" 等格式
        match = re.search(r'^(?:取消授权|revoke)\s*(.*)', text, re.I)
        if match and match.group(1).strip():
            return do_revoke(match.group(1).strip(), user_id)
        return "用法：取消授权 <用户名>"

    else:
        return do_query(text)


def do_query(keyword: str) -> str:
    # 先用本地智能搜索
    results = inventory.smart_query(keyword)
    if not results:
        results = inventory.query(keyword)
    
    # 如果本地没结果，使用 AI
    if not results and ai_processor:
        results = ai_processor.query_inventory(keyword, inventory.list_all())
        if results:
            return format_ai_results(results, keyword)
        else:
            return f"未找到匹配 '{keyword}' 的物料"
    
    if not results:
        return f"未找到匹配 '{keyword}' 的物料"
    
    return format_results(results, keyword)


def do_get_sheet_link() -> str:
    if not cloud_sheet:
        return "❌ 云表格功能未初始化"
    try:
        link = cloud_sheet.get_or_create()
        return f"📊 库存云表格链接：\n{link}\n\n所有人都可以查看这张表格"
    except Exception as e:
        return f"❌ 获取表格链接失败: {e}"


def do_sync_sheet() -> str:
    if not cloud_sheet:
        return "❌ 云表格功能未初始化"
    try:
        success, result = cloud_sheet.sync_inventory()
        if success:
            return f"✅ 库存已同步到云表格\n{result}"
        else:
            return f"❌ 同步失败: {result}"
    except Exception as e:
        return f"❌ 同步异常: {e}"


def get_category_name(keyword: str, item: dict) -> str:
    kw = keyword.lower()
    # Check keywords in priority order (longer/more specific matches first)
    for check_kw in ["led", "灯", "晶振", "crystal", "xtal", "二极管", "diode", "稳压", "zener",
                     "连接器", "connector", "fpc", "座", "排针", "header", "针座",
                     "开关", "switch", "蜂鸣器", "buzzer", "按键", "key", "button",
                     "晶体管", "mosfet", "mos", "保险丝", "fuse",
                     "电阻", "ohm", "ω", "电容", "f", "电感", "uh", "mh",
                     "芯片", "ic", "cpu", "mcu"]:
        if check_kw in kw:
            result = KEYWORD_TYPE_MAP.get(check_kw)
            if result:
                return result
    return item.get("name", "")


def _extract_package_size(package: str) -> str:
    """从封装字符串中提取标准封装尺寸"""
    if not package:
        return ""
    # 匹配 0402, 0603, 0805, 1206, 1210, 2010, 2512, SOT-23 等
    match = re.search(r'\b(0[48]0[235]|1[26]1[06]|2010|2512|SOT-?\d+|QFN|LQFP|SOP|DIP|TO-?\d+)\b', package, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # 尝试匹配电阻/电感封装如 R0603, C0603, L0603
    match = re.search(r'[RCL](\d{4})', package, re.IGNORECASE)
    if match:
        return match.group(1)
    return package


def format_results(results: list, keyword: str) -> str:
    if not results:
        return f"未找到包含 '{keyword}' 的物料"
    
    # 判断查询是否指定了组件类型
    component_type = None
    kw = keyword.lower()
    type_keywords = KEYWORD_TYPE_MAP
    for tk, tv in type_keywords.items():
        if tk in kw:
            component_type = tv
            break
    
    msg = f"找到 {len(results)} 条结果:\n\n"
    
    if component_type:
        # 指定了类型，简化表头：容值 | 封装 | 数量 | 上传人
        msg += f"{_pad('容值', 12)} | {_pad('封装', 12)} | {_pad('数量', 4)} | 上传人\n"
        msg += "-" * 50 + "\n"
        for item in results[:10]:
            owner = item.get('owner', item.get('上传人', ''))
            pkg = _extract_package_size(item.get('封装', ''))
            msg += f"{_pad(item.get('容值', ''), 12)} | {_pad(pkg, 12)} | {_pad(str(item.get('数量', 0)), 4)} | {owner}\n"
    else:
        # 未指定类型，显示完整表头
        msg += f"{_pad('类型', 6)} | {_pad('容值', 10)} | {_pad('封装', 12)} | {_pad('数量', 4)} | {_pad('生产商', 12)} | 上传人\n"
        msg += "-" * 70 + "\n"
        for item in results[:10]:
            display_type = get_category_name(keyword, item)
            owner = item.get('owner', item.get('上传人', ''))
            pkg = _extract_package_size(item.get('封装', ''))
            msg += f"{_pad(display_type, 6)} | {_pad(item.get('容值', ''), 10)} | {_pad(pkg, 12)} | "
            msg += f"{_pad(str(item.get('数量', 0)), 4)} | {_pad(item.get('生产商', ''), 12)} | {owner}\n"
    
    if len(results) > 10:
        msg += f"\n... 还有 {len(results) - 10} 条"
    return msg


def format_who_has(results: list, part_number: str) -> str:
    if not results:
        return f"未找到物料: {part_number}"
    msg = f"物料 '{part_number}' 归属情况:\n\n"
    msg += "类型 | 数量 | 封装 | 生产商\n"
    msg += "-" * 30 + "\n"
    for item in results:
        msg += f"{item.get('name', '')} | {item.get('quantity', 0)} | {item.get('封装', '')} | {item.get('manufacturer', '')}\n"
    return msg


def format_ai_results(results: list, query: str) -> str:
    if not results:
        return f"未找到匹配 '{query}' 的物料"
    msg = f"AI查询 '{query}' 找到 {len(results)} 条结果:\n\n"
    
    first = results[0] if results else {}
    has_owner = 'owner' in first or '上传人' in first
    
    if has_owner:
        msg += f"{_pad('类型', 6)} | {_pad('容值', 10)} | {_pad('封装', 20)} | {_pad('数量', 4)} | {_pad('生产商', 16)} | 上传人\n"
        msg += "-" * 80 + "\n"
        for item in results[:10]:
            owner = item.get('owner', item.get('上传人', ''))
            msg += f"{_pad(item.get('名称', ''), 6)} | {_pad(item.get('容值', ''), 10)} | {_pad(item.get('封装', ''), 20)} | "
            msg += f"{_pad(str(item.get('数量', 0)), 4)} | {_pad(item.get('生产商', ''), 16)} | {owner}\n"
    else:
        msg += f"{_pad('类型', 6)} | {_pad('容值', 10)} | {_pad('封装', 20)} | {_pad('数量', 4)} | {_pad('生产商', 16)}\n"
        msg += "-" * 70 + "\n"
        for item in results[:10]:
            msg += f"{_pad(item.get('名称', ''), 6)} | {_pad(item.get('容值', ''), 10)} | {_pad(item.get('封装', ''), 20)} | "
            msg += f"{_pad(str(item.get('数量', 0)), 4)} | {_pad(item.get('生产商', ''), 16)}\n"
    
    if len(results) > 10:
        msg += f"\n... 还有 {len(results) - 10} 条"
    return msg


def _pad(text: str, width: int) -> str:
    """按显示宽度填充，中文算2个字符"""
    import unicodedata
    display_width = sum(2 if unicodedata.east_asian_width(c) in 'FWA' else 1 for c in text)
    padding = width - display_width
    return text + ' ' * max(0, padding)


def format_list(items: list) -> str:
    if not items:
        return "库存为空"
    msg = f"库存列表 (共 {len(items)} 条):\n\n"
    msg += f"{_pad('类型', 6)} | {_pad('容值', 10)} | {_pad('封装', 20)} | {_pad('数量', 4)} | {_pad('生产商', 16)} | 上传人\n"
    msg += "-" * 80 + "\n"
    for item in items[:15]:
        msg += f"{_pad(item.get('名称', ''), 6)} | {_pad(item.get('容值', ''), 10)} | {_pad(item.get('封装', ''), 20)} | "
        msg += f"{_pad(str(item.get('数量', 0)), 4)} | {_pad(item.get('生产商', ''), 16)} | {item.get('上传人', '')}\n"
    if len(items) > 15:
        msg += f"\n... 还有 {len(items) - 15} 条"
    return msg


def get_help() -> str:
    return """BOM 库存管理命令:

- 上传 BOM 文件 (Excel/CSV) - 上传后选择"加入库存"或"摘取物料"
- 查询 [条件] - 搜索物料，支持：类型、容值、封装
- 谁有 [料号] - 查询物料归属
- 列表 - 查看所有库存
- 导出 - 导出库存表
- 链接 / 云表格 - 获取共享云表格链接
- 同步 - 手动将库存同步到云表格
- 录入 / 新增 - 手动录入物料到库存（逐条输入）
- 历史 - 查看上传历史
- 删除 <序号/时间戳> - 删除指定上传记录（需权限）
- 授权 <用户名> - 授予用户删除权限（仅超级管理员）
- 取消授权 <用户名> - 取消用户删除权限（仅超级管理员）
- 帮助 - 显示帮助

示例: 查询 100Ω 0402 电阻"""


def verify_feishu_signature(request_body: bytes, timestamp: str, nonce: str, signature: str, encrypt_key: str) -> bool:
    """验证飞书事件签名"""
    if not encrypt_key:
        return True  # 未配置密钥时跳过验证（开发环境）
    try:
        # 飞书签名算法: BASE64(SHA256(encrypt_key + timestamp + nonce + request_body))
        sign_str = encrypt_key + timestamp + nonce + request_body.decode('utf-8')
        expected = base64.b64encode(hashlib.sha256(sign_str.encode('utf-8')).digest()).decode('utf-8')
        return expected == signature
    except Exception as e:
        print(f"签名验证失败: {e}")
        return False


@app.route("/webhook", methods=["POST"])
def webhook():
    request_body = request.get_data()
    data = request.json
    print(f"[Webhook] Received: {data}")

    # 飞书事件签名验证
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")
    encrypt_key = os.getenv("LARK_ENCRYPT_KEY", "")

    if not verify_feishu_signature(request_body, timestamp, nonce, signature, encrypt_key):
        print(f"[Webhook] 签名验证失败")
        return jsonify({"code": 403, "msg": "invalid signature"}), 403

    event_type = data.get("header", {}).get("event_type") or data.get("type")

    if event_type == "url_verification":
        return jsonify({"challenge": data.get("challenge")})

    if event_type == "im.message.receive_v1":
        sender = data.get("event", {}).get("sender", {})
        message = data.get("event", {}).get("message", {})
        msg_id = message.get("message_id")
        chat_id = message.get("chat_id")
        msg_type = message.get("message_type", "")
        content = message.get("content", "")
        user_id = sender.get("sender_id", {}).get("open_id", "")

        if msg_id in processed_messages:
            return jsonify({"code": 0})
        processed_messages.add(msg_id)

        if len(processed_messages) > 1000:
            processed_messages.clear()

        if msg_type == "file":
            try:
                content_obj = json.loads(content)
                file_key = content_obj.get("file_key", "")
                if file_key:
                    reply = handle_file_upload(msg_id, file_key, user_id, chat_id)
                    send_message(msg_id, reply, chat_id=chat_id)
            except Exception as e:
                print(f"处理文件失败: {e}")
                send_message(msg_id, f"❌ 文件处理失败: {str(e)}", chat_id=chat_id)
            return jsonify({"code": 0})

        try:
            text_obj = json.loads(content)
            text = text_obj.get("text", "")
        except:
            text = content

        if text.startswith("/"):
            text = text[1:]

        reply = handle_command(text, user_id)
        send_message(msg_id, reply, chat_id=chat_id)

    return jsonify({"code": 0})


def get_user_name(user_id: str) -> str:
    try:
        from lark_oapi.api.contact.v3 import GetUserRequestBuilder
        
        request = GetUserRequestBuilder().user_id(user_id).build()
        response = client.contact.v3.user.get(request)
        user = response.data.user
        
        name = user.name if user else user_id
        return name
    except Exception as e:
        print(f"获取用户信息失败: {e}")
        return user_id


def download_file(message_id: str, file_key: str) -> str:
    temp_file = None
    try:
        from lark_oapi.api.im.v1 import (
            GetMessageResourceRequestBuilder,
            GetMessageResourceResponse
        )
        
        req = GetMessageResourceRequestBuilder().message_id(message_id).file_key(file_key).type("file").build()
        response = client.im.v1.message_resource.get(req)
        
        print(f"Get message resource response: success={response.success()}")
        
        if not response.success():
            raise Exception(f"获取下载链接失败: {response.code} {response.msg}")
        
        file_content = response.file.getvalue()
        print(f"File content size: {len(file_content)} bytes")
        
        ext = ".xlsx"
        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        temp_file.write(file_content)
        temp_file.close()
        
        return temp_file.name
    except Exception as e:
        print(f"下载文件失败: {e}")
        raise
    finally:
        # 注意：返回的文件路径需要由调用方清理
        pass


def upload_feishu_file(file_path: str) -> str | None:
    """上传文件到飞书文件服务器，返回 file_key"""
    from pathlib import Path
    file_path_obj = Path(file_path)
    file_name = file_path_obj.name
    
    # 获取 tenant_access_token
    token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(token_url, json={"app_id": config.LARK_APP_ID, "app_secret": config.LARK_APP_SECRET}, timeout=10)
        token_data = resp.json()
        if token_data.get("code") != 0:
            print(f"[Upload] 获取 token 失败: {token_data}")
            return None
        token = token_data["tenant_access_token"]
    except Exception as e:
        print(f"[Upload] 获取 token 异常: {e}")
        return None
    
    # 上传文件
    upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with open(file_path, "rb") as f:
            files = {
                "file": (file_name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "file_type": (None, "xls"),
                "file_name": (None, file_name),
            }
            resp = requests.post(upload_url, headers=headers, files=files, timeout=30)
            data = resp.json()
        
        if data.get("code") == 0:
            file_key = data["data"]["file_key"]
            print(f"[Upload] 文件上传成功: file_key={file_key}")
            return file_key
        else:
            print(f"[Upload] 文件上传失败: {data}")
            return None
    except Exception as e:
        print(f"[Upload] 文件上传异常: {e}")
        return None


def send_file_message(file_key: str, chat_id: str) -> bool:
    """发送文件消息到聊天"""
    token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(token_url, json={"app_id": config.LARK_APP_ID, "app_secret": config.LARK_APP_SECRET}, timeout=10)
        token_data = resp.json()
        if token_data.get("code") != 0:
            print(f"[SendFile] 获取 token 失败: {token_data}")
            return False
        token = token_data["tenant_access_token"]
    except Exception as e:
        print(f"[SendFile] 获取 token 异常: {e}")
        return False
    
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    body = {
        "receive_id": chat_id,
        "msg_type": "file",
        "content": json.dumps({"file_key": file_key}),
    }
    params = {"receive_id_type": "chat_id"}
    
    try:
        resp = requests.post(url, headers=headers, params=params, json=body, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            print(f"[SendFile] 文件消息发送成功: {file_key}")
            return True
        else:
            print(f"[SendFile] 文件消息发送失败: {data}")
            return False
    except Exception as e:
        print(f"[SendFile] 文件消息发送异常: {e}")
        return False


def handle_file_upload(message_id: str, file_key: str, user_id: str, chat_id: str) -> str:
    file_path = None
    try:
        from bom_processor import BOMProcessor
        
        timestamp = datetime.now().isoformat()
        user_name = get_user_name(user_id)
        file_path = download_file(message_id, file_key)
        
        print(f"[{timestamp}] 用户 {user_name} 上传了文件: {file_path}")
        
        items = BOMProcessor.read_file(file_path)
        print(f"读取到 {len(items)} 条物料记录")
        
        # 创建对话会话
        conversation_mgr.create(user_id, chat_id, items)
        conversation_mgr.update_state(user_id, STATE_SELECTING)
        
        return MODE_SELECT_MSG.format(count=len(items))
    except Exception as e:
        print(f"文件处理失败: {e}")
        return f"❌ 文件处理失败: {str(e)}"
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                print(f"清理临时文件失败: {e}")


def send_message(reply_to_id: str, text: str, chat_id: str = None):
    try:
        from lark_oapi.api.im.v1 import (
            CreateMessageRequestBuilder,
            CreateMessageRequestBodyBuilder,
        )

        body = (
            CreateMessageRequestBodyBuilder()
            .receive_id(chat_id or reply_to_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        request = (
            CreateMessageRequestBuilder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        client.im.v1.message.create(request)
    except Exception as e:
        print(f"发送消息失败: {e}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"[Feishu Bot] Starting... port: {port}")
    app.run(host="0.0.0.0", port=port)
