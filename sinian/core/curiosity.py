"""好奇心引擎 —— 让虚拟的 TA「活着」的那一层。

侧写完成那一刻，TA 不是被冻住了。一个爱看科技圈消息的人，
他的 AI 也该继续看科技圈的消息——这样有人来聊新发布的芯片时，
TA 能侃侃而谈，而不是只会聊侧写那年的旧闻。

三条规矩：
1. 学习方向由被侧写者的兴趣决定（interests + 擅长/了解的知识领域），
   不是别人觉得 TA 该学什么，也不是随便什么热点都追。
2. 风格意向同样管这里：本人说了"别让我碰理财"，引擎就不碰。
3. 学过的东西记日志（journal），每条带来源和日期，有据可查。
   没学过也不在原知识边界内的，坦然说不知道。

信息源（CuriositySource）是插件：RSS、新闻 API、定时抓取……社区实现。
核心只提供 ManualJsonSource 作样板和测试用。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

from sinian.core.persona import Persona


@dataclass
class JournalEntry:
    """一条自学记录：TA 在离开之后了解到的新东西。"""

    date: str                          # ISO 日期
    domain: str                        # 归属的兴趣方向
    content: str                       # 学到的事（摘要）
    source: str = "self-learning"


class CuriositySource(ABC):
    """信息源插件接口：吐出 [{topic, content, date?}, ...]。"""

    name: str = "unnamed"

    @abstractmethod
    def fetch(self) -> list[dict]:
        raise NotImplementedError


class ManualJsonSource(CuriositySource):
    """读本地 JSON 文件当信息源 —— 样板 + 测试用。

    格式：[{"topic": "科技数码", "content": "某厂商发布新芯片……"}]
    """

    name = "manual"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class CuriosityEngine:
    """从人格档案长出"关注方向"，再把信息源里对口的内容学进来。"""

    def __init__(self, persona: Persona, journal_path: str | Path):
        self.persona = persona
        self.journal_path = Path(journal_path)

    def directions(self) -> list[str]:
        """关注方向 = 兴趣 + 擅长/了解的知识领域。

        "不会"的领域不学（本人没兴趣是有原因的）；
        风格意向里否定过的方向同样尊重。
        """
        dirs: list[str] = list(self.persona.life.interests)
        for k in self.persona.knowledge:
            if k.level in ("擅长", "了解") and k.domain not in dirs:
                dirs.append(k.domain)
        # 意向否定过滤："别碰理财"这类意向在这里同样生效
        vetoed = " ".join(self.persona.style_directives)
        return [d for d in dirs if d not in vetoed]

    def learn(self, source: CuriositySource) -> list[JournalEntry]:
        """从信息源挑出对口方向的内容，记入学习日志。返回新学的条目。"""
        dirs = self.directions()
        if not dirs:
            return []
        new_entries = []
        for item in source.fetch():
            topic = item.get("topic", "")
            content = item.get("content", "")
            if not content:
                continue
            matched = next((d for d in dirs
                            if d in topic or topic in d
                            or any(k in content for k in [d])), None)
            if matched:
                new_entries.append(JournalEntry(
                    date=item.get("date") or date.today().isoformat(),
                    domain=matched,
                    content=content[:200],
                    source=source.name,
                ))
        if new_entries:
            self._append(new_entries)
        return new_entries

    def _append(self, entries: list[JournalEntry]) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

    def load_journal(self) -> list[JournalEntry]:
        if not self.journal_path.exists():
            return []
        out = []
        for line in self.journal_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(JournalEntry(**json.loads(line)))
        return out

    #: 检索时没信息量的口语 bigram，命中它们不算数
    STOP_BIGRAMS = {"最近", "什么", "有没", "消息", "怎么", "为啥", "那个",
                    "一下", "知道", "觉得", "现在", "你们", "我们"}

    def recall(self, query: str, limit: int = 5) -> list[JournalEntry]:
        """按对话内容检索相关自学记忆：对方聊什么，TA 想起什么。

        用 2 字滑窗做粗匹配——"芯片"从"最近芯片有什么新消息"里抠出来，
        命中日志里"新芯片发布"就算相关。比关键词表灵活，比 embedding 便宜。
        """
        hits = []
        for e in self.load_journal():
            haystack = e.domain + " " + e.content
            matched = any(
                bg in haystack
                for i in range(len(query) - 1)
                if (bg := query[i:i + 2]) not in self.STOP_BIGRAMS
                and not bg.isascii()
            )
            if matched or e.domain in query:
                hits.append(e)
        # 去重 + 最新优先
        seen, out = set(), []
        for e in reversed(hits):
            if e.content not in seen:
                seen.add(e.content)
                out.append(e)
            if len(out) >= limit:
                break
        return out
