import os
from pathlib import Path

# 支持 .env 文件（本地开发用）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INVENTORY_FILE = DATA_DIR / "inventory.json"
HISTORY_DIR = DATA_DIR / "history"

SQLITE_DB = DATA_DIR / "inventory.db"

DATA_DIR.mkdir(exist_ok=True)
HISTORY_DIR.mkdir(exist_ok=True)

# 所有密钥必须走环境变量，不能硬编码
LARK_APP_ID = os.getenv("LARK_APP_ID")
LARK_APP_SECRET = os.getenv("LARK_APP_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

BOM_FIELDS = ["Name", "Part Number", "Quantity", "Owner", "Location", "Notes"]

EXCEL_EXTENSIONS = [".xlsx", ".xls"]
CSV_EXTENSIONS = [".csv"]

AUTHORIZED_USERS_FILE = DATA_DIR / "authorized_users.json"