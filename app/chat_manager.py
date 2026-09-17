"""
Intelligent Chat & Task Session Management.
Ensures system prompts and subsequent turns for the same task/theme remain in
1 unified chat thread rather than creating dozens of fragmented chats on upstream providers.
"""

import hashlib
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.schemas import ChatCompletionRequest, ChatMessage

logger = logging.getLogger("chat_manager")


class ChatManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or settings.DATA_DIR) / "chats.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managed_chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    chat_id TEXT NOT NULL,
                    parent_id TEXT,
                    system_prompt TEXT,
                    first_prompt TEXT,
                    task_hash TEXT,
                    message_count INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_hash ON managed_chats(task_hash)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_id ON managed_chats(chat_id)"
            )
            conn.commit()

    @staticmethod
    def _clean_text(text: Optional[str]) -> str:
        if not text:
            return ""
        # Remove extra whitespace and normalize
        return re.sub(r"\s+", " ", text.strip().lower())

    def compute_task_fingerprint(
        self, messages: List[ChatMessage], provider: str
    ) -> Tuple[str, str, str, str]:
        """
        Derives task fingerprint from system prompt and first user prompt.
        Returns (task_hash, title, system_prompt, first_user_prompt).
        """
        system_prompt = ""
        first_user = ""

        for m in messages:
            if m.role == "system" and not system_prompt:
                system_prompt = m.get_text_content()
            elif m.role == "user" and not first_user:
                first_user = m.get_text_content()

        clean_sys = self._clean_text(system_prompt)
        clean_user = self._clean_text(first_user)

        # Title derivation
        title_source = first_user if first_user else (system_prompt if system_prompt else "New Task")
        title = title_source.strip().split("\n")[0][:45]
        if len(title_source.strip().split("\n")[0]) > 45:
            title += "..."

        # Hash: identifies conversations with the same core goal/prompt
        combined = f"{provider}:{clean_sys[:300]}:{clean_user[:300]}"
        task_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

        return task_hash, title, system_prompt, first_user

    def resolve_chat(
        self,
        request: ChatCompletionRequest,
        provider: str,
        http_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Determines whether this request belongs to an existing chat thread.
        """
        if getattr(request, "new_chat", False) or getattr(request, "newChat", False):
            logger.info("Request explicitly requested a new chat session.")
            return None

        # 1. Explicit conversation ID in body or headers
        explicit_id = (
            getattr(request, "conversation_id", None)
            or getattr(request, "chat_id", None)
            or getattr(request, "chatId", None)
        )
        if not explicit_id and http_headers:
            explicit_id = (
                http_headers.get("x-conversation-id")
                or http_headers.get("x-chat-id")
                or http_headers.get("x-session-id")
            )

        if explicit_id:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM managed_chats WHERE id = ? OR chat_id = ? LIMIT 1",
                    (explicit_id, explicit_id),
                ).fetchone()
                if row:
                    logger.info(f"Resolved existing chat via explicit ID: {row['chat_id']}")
                    return dict(row)

        # 2. Task fingerprint affinity matching
        if not request.messages:
            return None

        task_hash, title, sys_p, first_u = self.compute_task_fingerprint(
            request.messages, provider
        )
        timeout_window = time.time() - (60 * 60)  # 60 minute affinity window

        with self._connect() as conn:
            # Look for recent active chat with matching task fingerprint
            row = conn.execute(
                """
                SELECT * FROM managed_chats
                WHERE task_hash = ? AND provider = ? AND is_active = 1 AND updated_at >= ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (task_hash, provider, timeout_window),
            ).fetchone()

            if row:
                logger.info(
                    f"Matched prompt to existing task '{row['title']}' (chat_id: {row['chat_id']}, turns: {row['message_count']})"
                )
                return dict(row)

        return None

    def register_chat(
        self,
        chat_id: str,
        provider: str,
        model: str,
        messages: List[ChatMessage],
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registers a newly initiated upstream chat session under the task fingerprint.
        """
        task_hash, title, sys_p, first_u = self.compute_task_fingerprint(
            messages, provider
        )
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = time.time()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO managed_chats (
                    id, title, provider, model, chat_id, parent_id,
                    system_prompt, first_prompt, task_hash, message_count,
                    created_at, updated_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1)
                """,
                (
                    task_id,
                    title,
                    provider,
                    model,
                    chat_id,
                    parent_id,
                    sys_p,
                    first_u,
                    task_hash,
                    now,
                    now,
                ),
            )
            conn.commit()

        logger.info(f"Registered new managed task thread '{title}' -> chat_id: {chat_id}")
        return {
            "task_id": task_id,
            "title": title,
            "chat_id": chat_id,
            "parent_id": parent_id,
            "provider": provider,
        }

    def record_turn(
        self, chat_id: str, new_parent_id: Optional[str] = None
    ) -> None:
        """
        Updates the thread after a turn completes: advances message count and records new parent_id.
        """
        now = time.time()
        with self._connect() as conn:
            if new_parent_id:
                conn.execute(
                    """
                    UPDATE managed_chats
                    SET message_count = message_count + 1,
                        parent_id = ?,
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (new_parent_id, now, chat_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE managed_chats
                    SET message_count = message_count + 1,
                        updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (now, chat_id),
                )
            conn.commit()

    def list_chats(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, provider, model, chat_id, message_count, created_at, updated_at, is_active
                FROM managed_chats
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_chat(self, task_id_or_chat_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM managed_chats WHERE id = ? OR chat_id = ?",
                (task_id_or_chat_id, task_id_or_chat_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def reset_all_active(self) -> int:
        """Marks all chats as inactive so next prompts start fresh."""
        with self._connect() as conn:
            cur = conn.execute("UPDATE managed_chats SET is_active = 0 WHERE is_active = 1")
            conn.commit()
            return cur.rowcount

    def set_active(self, task_id_or_chat_id: str) -> bool:
        now = time.time()
        with self._connect() as conn:
            conn.execute("UPDATE managed_chats SET is_active = 0")
            cur = conn.execute(
                "UPDATE managed_chats SET is_active = 1, updated_at = ? WHERE id = ? OR chat_id = ?",
                (now, task_id_or_chat_id, task_id_or_chat_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_chat(self, task_id_or_chat_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM managed_chats WHERE id = ? OR chat_id = ? LIMIT 1",
                (task_id_or_chat_id, task_id_or_chat_id),
            ).fetchone()
            return dict(row) if row else None


chat_manager = ChatManager()
