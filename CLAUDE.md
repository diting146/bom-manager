# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# CLI — upload BOM file
py main.py upload <file.xlsx> --ai --export csv

# CLI — query inventory (substring match across all fields)
py main.py query "STM32F103"

# CLI — list inventory
py main.py list --limit 20

# CLI — check part ownership
py main.py who <part_number>

# CLI — export inventory
py main.py export --format csv

# CLI — view upload history
py main.py history --limit 10

# Start Feishu bot (Flask webhook)
py feishu_bot.py

# Install dependencies
pip install -r requirements.txt
```

## Project Architecture

- **feishu_bot.py** — Flask webhook, command parsing, message sending (single-threaded dev server)
- **inventory.py** — Inventory CRUD, history, rollback delete. SQLite backend with WAL mode.
- **conversation.py** — In-memory state machine for multi-step BOM upload flow (states: uploaded→selecting→confirming/completed)
- **bom_matcher.py** — BOM comparison, dedup, reduced-BOM Excel generation
- **cloud_sheet.py** — Feishu Bitable REST API sync
- **bom_processor.py** — Excel/CSV reading, type detection via designator prefix
- **ai_processor.py** — OpenRouter AI fallback for queries
- **component_types.py** — Centralized component type mapping
- **config.py** — Paths, env loading via python-dotenv

Key design decisions:
- Internal data fields use **Chinese keys** (`名称`, `封装`, `容值`, `料号`, `主人`)
- SQLite with WAL journal mode, one connection per operation (thread-safe for Flask)
- `BOMProcessor` is all static methods, no instance state
- AI processing failures are caught and degrade gracefully to local logic
- All secrets go through environment variables / `.env` file, never hardcoded

## Known Traps

1. **smart_query bug**: When query text contains no package keyword (0402/0603) and no value match, `matched_package` and `matched_value` default to True, returning ALL inventory instead of filtered results.

2. **Manual entry intercept**: In manual-entry mode, commands like `查询 xxx` / `历史` are intercepted (first-word matching) and user is prompted to send `完成` first.

3. **Old history can't be deleted**: Uploads from 2026-04-25 ~ 2026-04-26 lack `added_items` — deletion returns "旧记录不支持删除".

4. **Temp file leak**: `download_file()` in feishu_bot.py uses `delete=False`; cleanup only happens in `handle_file_upload()`.

5. **ngrok requires authtoken** on Linux first use, otherwise ERR_NGROK_4018.

6. **Chat logs** contain real user names — already gitignored but don't commit.
