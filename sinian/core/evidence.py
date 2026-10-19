"""EWPA —— 证据加权人格属性（Evidence-Weighted Persona Attributes）。

核心命题：人格的每个属性都不是一次蒸馏出的结论，
而是一条带置信度、带出处、带时间戳的「断言」（Claim）。

- 证据累积：每次侧写遇到支持同一断言的新证据，置信度单调上升、边际递减
  c' = 1 - (1 - c)(1 - w)
- 断言竞争：同一字段出现矛盾值（三个月前说做设计，半年后说转行运营），
  两条断言并存竞争，置信度高的胜出——人格会成长，旧我不会被删除只会被超越
- 阈值裁决：置信度低于 τ 的断言不进入生效人格——宁可未知，不可编造

这就是为什么人格学习可以是三个月、半年、一年：
档案不是结果，是一个不断成熟的证据体。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path


#: 证据来源的可信权重。本人亲口说的最重，统计推断最轻。
SOURCE_WEIGHTS = {
    "override": 1.0,        # 本人设定（身份层硬覆盖）
    "correction": 0.95,     # 亲友纠正
    "kinship": 0.9,         # 亲属称谓自称（"我妈"）
    "self_statement": 0.8,  # 本人自述（"我是做设计的"、"我不懂炒股"）
    "llm_inference": 0.5,   # LLM 从上下文归纳
    "statistical": 0.3,     # 统计推断（作息、兴趣命中）
}

DEFAULT_THRESHOLD = 0.6


@dataclass
class Claim:
    """一条人格断言。"""

    subject: str                     # 字段路径："life.occupation" / "identity.gender"
    value: str
    confidence: float
    source: str
    evidence: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""

    def reinforce(self, weight: float, evidence: str = "") -> None:
        """新证据加持：单调上升，边际递减。"""
        self.confidence = 1 - (1 - self.confidence) * (1 - weight)
        if evidence and evidence not in self.evidence and len(self.evidence) < 5:
            self.evidence.append(evidence)
        self.last_seen = date.today().isoformat()


class ClaimStore:
    """断言仓库：跨侧写批次累积，人格档案的证据底座。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.claims: list[Claim] = []
        if self.path and self.path.exists():
            self.claims = [Claim(**c) for c in
                           json.loads(self.path.read_text(encoding="utf-8"))]

    def add(self, subject: str, value: str, source: str, evidence: str = "") -> Claim:
        """记入一条证据。同值断言增强，异值断言并存竞争。"""
        weight = SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS["statistical"])
        value = value.strip()
        for c in self.claims:
            if c.subject == subject and c.value == value:
                c.reinforce(weight, evidence)
                return c
        claim = Claim(
            subject=subject, value=value, confidence=weight, source=source,
            evidence=[evidence] if evidence else [],
            first_seen=date.today().isoformat(),
            last_seen=date.today().isoformat(),
        )
        self.claims.append(claim)
        return claim

    def resolve(self, subject: str, threshold: float = DEFAULT_THRESHOLD) -> str | None:
        """裁决某个字段的生效值：最高置信度过阈值才生效，否则未知。"""
        candidates = [c for c in self.claims if c.subject == subject]
        if not candidates:
            return None
        best = max(candidates, key=lambda c: c.confidence)
        return best.value if best.confidence >= threshold else None

    def resolve_all(self, subject: str, threshold: float = DEFAULT_THRESHOLD) -> list[str]:
        """多值字段（如兴趣）：所有过阈值的值都生效。"""
        return [c.value for c in self.claims
                if c.subject == subject and c.confidence >= threshold]

    def table(self) -> list[Claim]:
        """按置信度排序的全量断言表——给人看的证据全貌。"""
        return sorted(self.claims, key=lambda c: -c.confidence)

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(c) for c in self.claims],
                           ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
