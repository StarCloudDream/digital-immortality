"""统一消息模型 —— 所有平台适配器的输出都必须长成这样。

不管你是从 QQ 导出的 txt 还是微信的解密数据库，到了这里都得归顺。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class UnifiedMessage:
    """一条聊天记录的最小完整表示。"""

    # 来自哪个平台（qq / wechat / telegram / ...），由适配器填
    platform: str

    # 会话标识：群号、私聊对象 id……同一对话串用同一个 id
    conversation_id: str

    # 发送者
    sender_id: str
    sender_name: str

    # 这条是不是"被侧写者本人"发的 —— 侧写引擎的锚点全靠它
    is_self: bool

    timestamp: datetime
    content: str

    # 消息类型：text / image / sticker / voice ...，非文本的占位即可
    msg_type: str = "text"

    # 引用/回复了哪条消息（可选，能显著提升上下文理解）
    reply_to: Optional[str] = None

    # 平台特有的杂项，塞这里，别往主模型里加字段
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "UnifiedMessage":
        d = dict(d)
        d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        # 手改 messages.json 是允许的，但删了键得说清楚少了什么——
        # 一个光秃秃的 TypeError 能把人逼疯
        required = {"platform", "conversation_id", "sender_id",
                    "sender_name", "is_self", "content"}
        missing = required - d.keys()
        if missing:
            raise ValueError(
                f"这条消息缺字段：{sorted(missing)}。"
                f"messages.json 可以手改，但别删键——"
                f"拿不准就先删掉整份文件重新 sinian ingest。"
            )
        return cls(**d)
