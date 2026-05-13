import argparse
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import config
from bom_processor import BOMProcessor
from ai_processor import AIProcessor
from inventory import InventoryManager


def upload_bom(args):
    file_path = args.file
    if not Path(file_path).exists():
        print(f"错误: 文件不存在: {file_path}")
        return 1

    print(f"==> 正在读取文件: {file_path}")
    items = BOMProcessor.read_file(file_path)
    print(f"   读取到 {len(items)} 条物料记录")

    if args.ai and config.OPENAI_API_KEY:
        print("==> 正在使用AI整理...")
        try:
            ai = AIProcessor()
            organized = ai.organize_items(items)
            items = organized
            print(f"   AI整理完成，共 {len(items)} 条")
        except Exception as e:
            print(f"   AI整理失败: {e}")
            print("   使用原始数据继续...")

    print("==> 正在保存到库存...")
    manager = InventoryManager()
    manager.add_items(items)
    print("   保存成功!")

    if args.export:
        output = manager.export(args.export)
        print(f"📊 已导出到: {output}")

    return 0


def query_item(args):
    manager = InventoryManager()
    results = manager.query(args.keyword)

    if not results:
        print(f"未找到包含 '{args.keyword}' 的物料")
        return 0

    print(f"找到 {len(results)} 条结果:\n")
    print(f"{'名称':<20} {'料号':<25} {'数量':<6} {'生产商':<20} {'供应商':<10}")
    print("-" * 85)
    for item in results:
        print(f"{item.get('name', ''):<20} {item.get('part_number', ''):<25} "
              f"{item.get('quantity', 0):<6} {item.get('manufacturer', ''):<20} {item.get('supplier', ''):<10}")
    return 0


def who_has(args):
    manager = InventoryManager()
    results = manager.who_has(args.part_number)

    if not results:
        print(f"未找到物料: {args.part_number}")
        return 0

    print(f"📍 物料 '{args.part_number}' 归属情况:\n")
    print(f"{'名称':<20} {'料号':<25} {'数量':<6} {'生产商':<20} {'供应商':<10}")
    print("-" * 85)
    for item in results:
        print(f"{item.get('name', ''):<20} {item.get('part_number', ''):<25} "
              f"{item.get('quantity', 0):<6} {item.get('manufacturer', ''):<20} {item.get('supplier', ''):<10}")
    return 0


def list_inventory(args):
    manager = InventoryManager()
    items = manager.list_all()

    if not items:
        print("库存为空，请先上传BOM文件")
        return 0

    limit = args.limit
    display_items = items[:limit] if limit else items

    print(f"📦 库存列表 (共 {len(items)} 条):\n")
    print(f"{'名称':<20} {'料号':<25} {'数量':<6} {'生产商':<20} {'供应商':<10}")
    print("-" * 85)
    for item in display_items:
        print(f"{item.get('name', ''):<20} {item.get('part_number', ''):<25} "
              f"{item.get('quantity', 0):<6} {item.get('manufacturer', ''):<20} {item.get('supplier', ''):<10}")

    if limit and len(items) > limit:
        print(f"\n... 还有 {len(items) - limit} 条记录，使用 --limit 查看更多")

    return 0


def export_inventory(args):
    manager = InventoryManager()
    output = manager.export(args.format)
    print(f"📊 已导出到: {output}")
    return 0


def show_history(args):
    manager = InventoryManager()
    history = manager.history
    
    if not history:
        print("暂无上传历史")
        return 0
    
    limit = args.limit
    display = history[-limit:][::-1]
    
    print(f"📜 上传历史 (共 {len(history)} 条):\n")
    print(f"{'时间':<25} {'上传人':<10} {'数量'}")
    print("-" * 50)
    for h in display:
        print(f"{h.get('time', ''):<25} {h.get('owner', ''):<10} {h.get('count', 0)}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="BOM智能库存管理系统")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    upload_parser = subparsers.add_parser("upload", help="上传BOM文件")
    upload_parser.add_argument("file", help="BOM文件路径 (xlsx/xls/csv)")
    upload_parser.add_argument("--ai", action="store_true", help="使用AI整理")
    upload_parser.add_argument("--export", choices=["excel", "csv"], help="导入后导出")

    query_parser = subparsers.add_parser("query", help="查询物料")
    query_parser.add_argument("keyword", help="搜索关键词")

    who_parser = subparsers.add_parser("who", help="查询谁有某物料")
    who_parser.add_argument("part_number", help="物料料号或名称")

    list_parser = subparsers.add_parser("list", help="列出所有库存")
    list_parser.add_argument("--limit", type=int, default=20, help="显示数量限制")

    export_parser = subparsers.add_parser("export", help="导出库存")
    export_parser.add_argument("--format", choices=["excel", "csv"], default="excel", help="导出格式")

    history_parser = subparsers.add_parser("history", help="查看上传历史")
    history_parser.add_argument("--limit", type=int, default=10, help="显示数量限制")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "upload": upload_bom,
        "query": query_item,
        "who": who_has,
        "list": list_inventory,
        "export": export_inventory,
        "history": show_history
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())