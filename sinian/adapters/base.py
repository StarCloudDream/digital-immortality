"""数据源适配器接口 —— 社区开发者要实现的只有这一个类。

设计原则：核心仓库永远不绑定任何具体平台。
你怎么拿到聊天记录（导出文件、协议逆向、数据库解密……）是你自己的事，
只要你最后能吐出一串 UnifiedMessage，人格引擎就接管后面的一切。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from sinian.core.message import UnifiedMessage


class ChatSourceAdapter(ABC):
    """聊天记录来源适配器基类。"""

    #: 适配器名字，比如 "qq_export"、"wechat_db"
    name: str = "unnamed"

    @abstractmethod
    def fetch(self, source: str, **kwargs) -> Iterator[UnifiedMessage]:
        """从 source（文件路径/数据库目录/随便什么）产出统一消息流。

        要求：
        - 流式产出（yield），别一口气把几十万条全塞内存里
        - 必须正确标记 is_self —— 这是整个侧写系统的锚点
        - 按时间顺序产出
        """
        raise NotImplementedError

    def describe(self) -> str:
        """给人看的说明：这个适配器吃什么格式的输入。"""
        return self.__doc__ or ""
