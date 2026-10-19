"""示例适配器 —— 读取一个最简单的 JSON 导出格式，给社区当模板用。

格式示例见 examples/sample_chat.json。新平台的适配器照着这个抄就行。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterator

from sinian.adapters.base import ChatSourceAdapter
from sinian.core.message import UnifiedMessage


class TemplateJsonAdapter(ChatSourceAdapter):
    """读取 [{platform, conversation_id, sender_id, sender_name, is_self,
    timestamp, content, ...}, ...] 这样的 JSON 数组。"""

    name = "template"

    def fetch(self, source: str, **kwargs) -> Iterator[UnifiedMessage]:
        with open(source, "r", encoding="utf-8") as f:
            rows = json.load(f)
        for row in sorted(rows, key=lambda r: r["timestamp"]):
            yield UnifiedMessage(
                platform=row.get("platform", "template"),
                conversation_id=row["conversation_id"],
                sender_id=row["sender_id"],
                sender_name=row["sender_name"],
                is_self=bool(row["is_self"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                content=row["content"],
                msg_type=row.get("msg_type", "text"),
                reply_to=row.get("reply_to"),
            )
