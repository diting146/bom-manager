"""Centralized component type mappings - single source of truth.

All files should import from here instead of duplicating maps.
This module is dependency-free by design.
"""

# All valid type names
ALL_TYPES = [
    "电阻", "电容", "电感", "芯片", "二极管", "晶体管",
    "晶振", "连接器", "排针", "开关", "蜂鸣器", "LED",
    "保险丝", "测试点", "其他",
]

# Designator prefix → type name (longer prefixes first priority)
# Used by bom_processor.py to classify components from BOM designators
DESIGNATOR_TYPE_MAP = {
    "R": "电阻",
    "C": "电容",
    "L": "电感",
    "U": "芯片",
    "IC": "芯片",
    "D": "二极管",
    "LED": "二极管",
    "Q": "晶体管",
    "Y": "晶振",
    "X": "晶振",
    "OSC": "晶振",
    "H": "连接器",
    "J": "连接器",
    "P": "连接器",
    "F": "保险丝",
    "S": "开关",
    "SW": "开关",
    "B": "蜂鸣器",
    "TP": "测试点",
}

# Keyword → single type name (for display purposes)
# Used by feishu_bot.py get_category_name / format_results
KEYWORD_TYPE_MAP = {
    "电阻": "电阻", "resistor": "电阻",
    "电容": "电容", "capacitor": "电容",
    "电感": "电感", "inductor": "电感",
    "芯片": "芯片", "ic": "芯片", "chip": "芯片",
    "二极管": "二极管", "diode": "二极管", "稳压": "二极管", "zener": "二极管",
    "晶体管": "晶体管", "mos": "晶体管", "mosfet": "晶体管",
    "晶振": "晶振", "crystal": "晶振",
    "连接器": "连接器", "connector": "连接器", "conn": "连接器",
    "排针": "排针", "header": "排针",
    "开关": "开关", "switch": "开关",
    "蜂鸣器": "蜂鸣器", "buzzer": "蜂鸣器",
    "led": "LED", "灯": "LED",
    "保险丝": "保险丝", "fuse": "保险丝", "ferrite": "保险丝", "磁珠": "保险丝",
    # Single-letter fallbacks for feishu_bot format_results type_keywords
    "r": "电阻", "c": "电容", "l": "电感",
    "d": "二极管", "q": "晶体管",
    "y": "晶振", "x": "晶振",
    "h": "连接器", "j": "连接器", "p": "连接器",
    "s": "开关", "sw": "开关", "b": "蜂鸣器",
    "f": "电容",  # 'f' alone maps to capacitor in feishu formatting
}

# Keyword → list of type names (for smart_query multi-type filtering)
# Used by inventory.py to broaden search matches
KEYWORD_TO_TYPES = {
    "电阻": ["电阻"], "resistor": ["电阻"], "r": ["电阻"],
    "电容": ["电容"], "capacitor": ["电容"], "c": ["电容"], "f": ["电容"],
    "电感": ["电感"], "inductor": ["电感"], "l": ["电感"],
    "芯片": ["芯片"], "ic": ["芯片"], "chip": ["芯片"], "u": ["芯片"],
    "二极管": ["二极管"], "diode": ["二极管"], "d": ["二极管"],
    "晶体管": ["晶体管"], "mos": ["晶体管"], "mosfet": ["晶体管"], "q": ["晶体管"],
    "晶振": ["晶振"], "crystal": ["晶振"], "y": ["晶振"], "x": ["晶振"],
    "连接器": ["连接器", "排针"], "connector": ["连接器", "排针"], "conn": ["连接器", "排针"],
    "h": ["连接器", "排针"], "j": ["连接器", "排针"], "p": ["连接器", "排针"],
    "排针": ["排针", "连接器"], "header": ["排针", "连接器"],
    "开关": ["开关"], "switch": ["开关"], "sw": ["开关"], "s": ["开关"],
    "蜂鸣器": ["蜂鸣器"], "buzzer": ["蜂鸣器"], "b": ["蜂鸣器"],
    "led": ["LED"], "灯": ["LED"],
    "保险丝": ["保险丝"], "fuse": ["保险丝"], "ferrite": ["保险丝"], "磁珠": ["保险丝"],
}


def classify_by_designator(designator: str) -> str:
    """根据位号前缀识别组件类型

    Args:
        designator: 位号 (e.g. "R1", "IC3", "LED2")

    Returns:
        对应的类型名称，无匹配返回"其他"
    """
    if not designator:
        return "其他"
    d_upper = designator.upper().strip()
    for prefix, type_name in sorted(
        DESIGNATOR_TYPE_MAP.items(), key=lambda x: -len(x[0])
    ):
        if d_upper.startswith(prefix):
            return type_name
    return "其他"


def classify_by_keyword(keyword: str) -> str | None:
    """根据关键词返回组件类型（用于显示），无匹配返回 None

    Args:
        keyword: 搜索关键词

    Returns:
        类型名称，无匹配返回 None
    """
    keyword = keyword.lower()
    return KEYWORD_TYPE_MAP.get(keyword)


def get_matching_type_names(keyword: str) -> list[str]:
    """根据关键词返回匹配的组件类型列表（用于过滤），无匹配返回空列表

    Args:
        keyword: 搜索关键词

    Returns:
        匹配的类型名称列表，无匹配返回空列表
    """
    keyword = keyword.lower()
    return KEYWORD_TO_TYPES.get(keyword, [])
