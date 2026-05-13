"""Multi-step conversation state manager for Feishu BOM bot.

Tracks user upload -> mode selection -> action -> completion flow.
In-memory only, no persistence. Designed for single-threaded Flask dev server.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ── State constants ──────────────────────────────────────────────

STATE_UPLOADED = "uploaded"          # 已上传文件，等待选择模式
STATE_SELECTING = "selecting"        # 已发送模式选择，等待用户回复
STATE_CONFIRMING = "confirming"      # 已发送重复项列表，等待确认操作
STATE_MANUAL_PACKAGE = "manual_package"  # 手动录入—等待输入封装
STATE_MANUAL_INPUT = "manual_input"  # 手动录入—输入容值
STATE_COMPLETED = "completed"        # 操作完成
STATE_EXPIRED = "expired"            # 超时过期

# ── Mode constants ───────────────────────────────────────────────

MODE_ADD = "add"                     # 加入库存
MODE_EXTRACT = "extract"             # 摘取物料

# ── Bot message templates ────────────────────────────────────────

MODE_SELECT_MSG = """✅ BOM 文件已解析完成！共 {count} 条物料。

请选择操作：
1️⃣ 加入库存 — 将物料合并到库存总表
2️⃣ 摘取物料 — 对比库存，移除已有物料"""

DUPLICATE_SUMMARY_MSG = """🔍 对比结果：
BOM 中 {duplicate_count}/{total_count} 条已存在于库存：
{duplicate_list}

请选择：
1️⃣ 移除重复项，生成精简 BOM（剩余 {remaining_count} 条）
2️⃣ 保留所有物料，不做处理"""

MANUAL_INPUT_HELP = """📝 手动录入模式

请逐条输入物料，每行一条，格式：
`容值, 封装`

示例：
10kΩ, 0402
47uF, C0603
100Ω, 0805

系统会自动识别类型（电阻/电容/电感）
输入完成后，发送"完成"结束录入并入库
发送"取消"放弃本次操作"""

MANUAL_PACKAGE_PROMPT = """📝 批量录入模式

请输入统一封装（如 0402、C0603、0805 等）：

输入封装后，你只需逐条输入容值即可，系统会自动套用封装
发送"取消"放弃本次操作"""


# ── Data model ───────────────────────────────────────────────────

@dataclass
class Conversation:
    """Represents a single multi-step conversation session.

    Attributes:
        user_id: Feishu open_id (unique per user).
        chat_id: Chat session ID.
        state: Current state — one of STATE_* constants.
        uploaded_items: Parsed BOM items list.
        uploaded_count: Number of items originally uploaded.
        selected_mode: User-chosen mode — 'add' or 'extract'.
        matched_results: Comparison results for extract mode.
        created_at: ISO-format creation timestamp.
        last_active: ISO-format last-activity timestamp.
    """

    user_id: str
    chat_id: str
    state: str
    uploaded_items: list[dict]
    uploaded_count: int
    selected_mode: Optional[str] = None
    matched_results: Optional[dict] = None
    batch_package: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())


# ── Manager ──────────────────────────────────────────────────────

class ConversationManager:
    """Manages in-memory conversation sessions.

    Thread-safe assumptions: designed for Flask single-threaded dev server.
    No persistence — all state is lost on restart.

    SESSION_TIMEOUT: seconds of inactivity before a session is considered expired.
    MAX_SESSIONS: maximum number of active sessions before oldest are cleaned up.
    """

    SESSION_TIMEOUT = 600   # 10 minutes
    MAX_SESSIONS = 500      # soft cap; oldest evicted when exceeded

    def __init__(self) -> None:
        self._sessions: dict[str, Conversation] = {}

    # ── Public API ───────────────────────────────────────────────

    def create(self, user_id: str, chat_id: str, items: list[dict]) -> Conversation:
        """Create a new conversation session.

        If the user already has an active session it is silently replaced
        (the old session is discarded).

        Args:
            user_id: Feishu open_id (unique per user).
            chat_id: Chat session ID.
            items: Parsed BOM items list.

        Returns:
            The newly created Conversation.
        """
        session = Conversation(
            user_id=user_id,
            chat_id=chat_id,
            state=STATE_UPLOADED,
            uploaded_items=items,
            uploaded_count=len(items),
        )
        self._sessions[user_id] = session
        self._cleanup()
        return session

    def get(self, user_id: str) -> Optional[Conversation]:
        """Get the user's current active session.

        Returns *None* when:
        - No session exists for this user.
        - Session has expired (inactivity longer than *SESSION_TIMEOUT*).

        Expired sessions are automatically removed from the store.

        Args:
            user_id: Feishu open_id.

        Returns:
            Conversation or None.
        """
        session = self._sessions.get(user_id)
        if session is None:
            return None

        last_active = datetime.fromisoformat(session.last_active)
        now = datetime.now()
        if (now - last_active).total_seconds() > self.SESSION_TIMEOUT:
            session.state = STATE_EXPIRED
            del self._sessions[user_id]
            return None

        return session

    def update_state(self, user_id: str, state: str) -> bool:
        """Update the state of a user's session.

        Returns *False* if no session exists or the session is expired.
        Does **not** validate state transitions — that is the caller's
        responsibility.

        Args:
            user_id: Feishu open_id.
            state: One of the STATE_* constants.

        Returns:
            True if updated, False on failure.
        """
        session = self.get(user_id)
        if session is None:
            return False
        session.state = state
        self._touch(user_id)
        return True

    def select_mode(self, user_id: str, mode: str) -> bool:
        """Record the user's selected operation mode.

        Validates:
        - Current state is ``selecting``.
        - *mode* is ``'add'`` or ``'extract'``.

        State transitions:
        - ``'add'`` → state becomes ``completed`` (no further steps).
        - ``'extract'`` → state stays ``selecting`` (awaiting matched results
          via :meth:`set_matched_results`).

        Args:
            user_id: Feishu open_id.
            mode: ``'add'`` or ``'extract'``.

        Returns:
            True if successful, False if validation fails.
        """
        session = self.get(user_id)
        if session is None:
            return False
        if session.state != STATE_SELECTING:
            return False
        if mode not in (MODE_ADD, MODE_EXTRACT):
            return False

        session.selected_mode = mode
        if mode == MODE_ADD:
            session.state = STATE_COMPLETED

        self._touch(user_id)
        return True

    def set_matched_results(self, user_id: str, results: dict) -> bool:
        """Store comparison results for extract mode.

        Validates:
        - User already selected ``'extract'`` mode.
        - Current state is ``selecting``.

        State transition: → ``confirming``.

        Args:
            user_id: Feishu open_id.
            results: Comparison result dict (shape defined by caller).

        Returns:
            True if successful, False if validation fails.
        """
        session = self.get(user_id)
        if session is None:
            return False
        if session.selected_mode != MODE_EXTRACT:
            return False
        if session.state != STATE_SELECTING:
            return False

        session.matched_results = results
        session.state = STATE_CONFIRMING
        self._touch(user_id)
        return True

    def complete(self, user_id: str) -> bool:
        """Mark a session as completed.

        Validates that current state is ``'confirming'`` (extract flow)
        or ``'selecting'`` (add flow, as a safety net).

        State transition: → ``completed``.

        Args:
            user_id: Feishu open_id.

        Returns:
            True if successful, False if validation fails.
        """
        session = self.get(user_id)
        if session is None:
            return False
        if session.state not in (STATE_CONFIRMING, STATE_SELECTING, STATE_MANUAL_INPUT, STATE_MANUAL_PACKAGE):
            return False

        session.state = STATE_COMPLETED
        self._touch(user_id)
        return True

    def clear_expired(self) -> None:
        """Remove all expired sessions.

        Iterates through all sessions and removes those whose inactivity
        exceeds *SESSION_TIMEOUT*. Their state is set to ``expired``
        before removal.
        """
        now = datetime.now()
        expired_keys: list[str] = []
        for user_id, session in self._sessions.items():
            last_active = datetime.fromisoformat(session.last_active)
            if (now - last_active).total_seconds() > self.SESSION_TIMEOUT:
                session.state = STATE_EXPIRED
                expired_keys.append(user_id)

        for key in expired_keys:
            del self._sessions[key]

    # ── Internals ────────────────────────────────────────────────

    def _touch(self, user_id: str) -> bool:
        """Refresh the ``last_active`` timestamp of a session."""
        session = self._sessions.get(user_id)
        if session is None:
            return False
        session.last_active = datetime.now().isoformat()
        return True

    def _cleanup(self) -> None:
        """Enforce *MAX_SESSIONS* limit by evicting the oldest sessions.

        Runs on every :meth:`create` call.  Removed sessions have their
        state set to ``expired``.
        """
        if len(self._sessions) <= self.MAX_SESSIONS:
            return

        # Sort by last_active ascending (oldest first)
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda kv: kv[1].last_active,
        )

        excess = len(self._sessions) - self.MAX_SESSIONS
        for i in range(excess):
            user_id, session = sorted_sessions[i]
            session.state = STATE_EXPIRED
            del self._sessions[user_id]

    # For backwards-compatible public access
    cleanup = _cleanup
