import pandas as pd
from pathlib import Path
import config


class BOMProcessor:
    @staticmethod
    def read_file(file_path: str) -> list:
        path = Path(file_path)
        ext = path.suffix.lower()
        
        if ext in config.EXCEL_EXTENSIONS:
            return BOMProcessor._read_excel(path)
        elif ext in config.CSV_EXTENSIONS:
            return BOMProcessor._read_csv(path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    @staticmethod
    def _read_excel(path: Path) -> list:
        for header in range(10):
            try:
                df = pd.read_excel(path, header=header)
                if 'No.' in df.columns or 'Quantity' in df.columns:
                    return BOMProcessor._normalize_dataframe(df)
            except:
                continue
        df = pd.read_excel(path)
        return BOMProcessor._normalize_dataframe(df)

    @staticmethod
    def _read_csv(path: Path) -> list:
        df = pd.read_csv(path)
        return BOMProcessor._normalize_dataframe(df)

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> list:
        items = []
        
        for _, row in df.iterrows():
            designator = str(row.get("Designator", "")).strip()
            if designator.lower() == "nan" or designator == "":
                continue
            
            part_number = str(row.get("Manufacturer Part", "")).strip()
            if part_number.lower() == "nan":
                part_number = ""
            
            value = str(row.get("Value", "")).strip()
            if value.lower() == "nan":
                value = ""
            
            quantity_val = row.get("Quantity", 1)
            try:
                quantity = int(float(quantity_val)) if pd.notna(quantity_val) else 1
            except:
                quantity = 1
            
            manufacturer = str(row.get("Manufacturer", "")).strip()
            if manufacturer.lower() == "nan":
                manufacturer = ""
            supplier = str(row.get("Supplier", "")).strip()
            if supplier.lower() == "nan":
                supplier = ""
            comment = str(row.get("Comment", "")).strip()
            if comment.lower() == "nan":
                comment = ""
            footprint = str(row.get("Footprint", "")).strip()
            if footprint.lower() == "nan":
                footprint = ""
            
            d_upper = designator.upper()
            if d_upper.startswith("R"):
                component_type = "电阻"
            elif d_upper.startswith("C"):
                component_type = "电容"
            elif d_upper.startswith("L"):
                component_type = "电感"
            elif d_upper.startswith("U") or d_upper.startswith("IC"):
                component_type = "芯片"
            elif d_upper.startswith("D") or d_upper.startswith("LED"):
                component_type = "二极管"
            elif d_upper.startswith("Q"):
                component_type = "晶体管"
            elif d_upper.startswith("Y") or d_upper.startswith("X") or d_upper.startswith("OSC"):
                component_type = "晶振"
            elif d_upper.startswith("H") or d_upper.startswith("J") or d_upper.startswith("P"):
                component_type = "连接器"
            elif d_upper.startswith("F"):
                component_type = "保险丝"
            elif d_upper.startswith("S") or d_upper.startswith("SW"):
                component_type = "开关"
            elif d_upper.startswith("B"):
                component_type = "蜂鸣器"
            elif d_upper.startswith("TP"):
                component_type = "测试点"
            else:
                component_type = "其他"
            
            items.append({
                "名称": component_type,
                "封装": footprint,
                "容值": value,
                "数量": quantity,
                "料号": part_number,
                "生产商": manufacturer,
                "供应商": supplier,
                "备注": comment,
                "主人": "",
                "designator": designator
            })
        return items

    @staticmethod
    def export_to_excel(data: list, output_path: str):
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    @staticmethod
    def export_to_csv(data: list, output_path: str):
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False)
        return output_path