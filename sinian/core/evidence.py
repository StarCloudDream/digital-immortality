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

#: 证据等级（三级制，但做了自己的改动）：
#: verbatim 本人原话 > artifact 文档材料 > impression 印象与统计推断
LEVEL_MULTIPLIER = {"verbatim": 1.0, "artifact": 0.8, "impression": 0.5}

#: 来源默认对应的证据等级——本人亲口说的算原话，统计推断只能算印象
SOURCE_LEVEL = {
    "override": "verbatim", "correction": "verbatim", "kinship": "verbatim",
    "self_statement": "verbatim", "llm_inference": "impression",
    "statistical": "impression",
}

#: 印象级断言要进入生效人格，得拿出压倒性的置信度（0.9）。
#:  eligible() 门控：不是所有高分都能上路
IMPRESSION_GATE = 0.9


@dataclass
class Claim:
    """一条人格断言。"""

    subject: str                     # 字段路径："life.occupation" / "identity.gender"
    value: str
    confidence: float
    source: str
    level: str = "verbatim"          # verbatim / artifact / impression
    evidence: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    #: 已计入的证据指纹。同一条证据反复出现不该把置信度刷上天——
    #:  canonical_id 去重计权
    counted: list[str] = field(default_factory=list)
    #: 被撤回。本人说"这条不算数"，断言保留在仓库里但不再生效
    revoked: bool = False

    def reinforce(self, weight: float, evidence: str = "") -> bool:
        """新证据加持：单调上升，边际递减。同一条证据只算一次。

        返回是否真的加持了（重复证据返回 False）。
        """
        if evidence:
            fp = "".join(ch for ch in evidence if not ch.isspace())
            if fp in self.counted:
                return False
            if len(self.counted) < 30:
                self.counted.append(fp)
        effective = weight * LEVEL_MULTIPLIER.get(self.level, 0.5)
        self.confidence = 1 - (1 - self.confidence) * (1 - effective)
        if evidence and len(self.evidence) < 5:
            self.evidence.append(evidence)
        self.last_seen = date.today().isoformat()
        return True

    def ready(self, threshold: float = DEFAULT_THRESHOLD) -> bool:
        """资格门控：撤回的不算；印象级断言要压倒性置信度才生效。

        这条是 EWPA 的"硬闸门"——不是所有高分断言都能进入人格，
        印象级的猜测必须强到离谱才配被称为事实。
        """
        if self.revoked:
            return False
        need = IMPRESSION_GATE if self.level == "impression" else threshold
        return self.confidence >= need


class ClaimStore:
    """断言仓库：跨侧写批次累积，人格档案的证据底座。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.claims: list[Claim] = []
        if self.path and self.path.exists():
            self.claims = [Claim(**c) for c in
                           json.loads(self.path.read_text(encoding="utf-8"))]

    def add(self, subject: str, value: str, source: str, evidence: str = "",
            level: str | None = None) -> Claim:
        """记入一条证据。同值断言增强，异值断言并存竞争。

        level 可显式指定证据等级（verbatim/artifact/impression），
        不指定就按来源默认——统计推断自动降为 impression，
        所以纯猜测很难混进生效人格。
        """
        weight = SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS["statistical"])
        lvl = level or SOURCE_LEVEL.get(source, "verbatim")
        value = value.strip()
        for c in self.claims:
            if c.subject == subject and c.value == value:
                # 等级往上抬：原话级证据能把印象级断言扶正
                if lvl == "verbatim" or (lvl == "artifact" and c.level == "impression"):
                    c.level = lvl
                c.reinforce(weight, evidence)
                return c
        fp = "".join(ch for ch in evidence if not ch.isspace()) if evidence else ""
        claim = Claim(
            subject=subject, value=value, confidence=weight, source=source,
            level=lvl,
            evidence=[evidence] if evidence else [],
            counted=[fp] if fp else [],
            first_seen=date.today().isoformat(),
            last_seen=date.today().isoformat(),
        )
        self.claims.append(claim)
        return claim

    def retract(self, subject: str, value: str) -> bool:
        """撤回一条断言。断言留在仓库里（保留历史），但不再生效。

        本人说"这条不算数"就该真不算数——某开源项目 那种
        "提交后不可撤回"的设计是我们明确要避免的反面。
        """
        hit = False
        for c in self.claims:
            if c.subject == subject and c.value == value:
                c.revoked = True
                hit = True
        return hit

    def resolve(self, subject: str, threshold: float = DEFAULT_THRESHOLD) -> str | None:
        """裁决某个字段的生效值：过资格门且最高置信者胜出，否则未知。"""
        candidates = [c for c in self.claims
                      if c.subject == subject and c.ready(threshold)]
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.confidence).value

    def resolve_all(self, subject: str, threshold: float = DEFAULT_THRESHOLD) -> list[str]:
        """多值字段（如兴趣）：所有过门的值都生效。"""
        return [c.value for c in self.claims
                if c.subject == subject and c.ready(threshold)]

    def verbatim_ratio(self) -> float:
        """原话级断言占比——人格质量的核心指标（量化门槛）。"""
        active = [c for c in self.claims if not c.revoked]
        if not active:
            return 0.0
        return sum(1 for c in active if c.level == "verbatim") / len(active)

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
