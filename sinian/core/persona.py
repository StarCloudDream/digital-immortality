"""人格模型 —— 这个项目的灵魂。

人格分两层：
- 身份层（identity）：性别、年龄、自称、身材描述…… 侧写会推断，
  本人的「身份设定」拥有最高优先级，强制覆盖。
- 风格层（style）：口头禅、幽默度、句长分布、emoji 习惯…… 从数据里学。

但风格层不是神圣不可碰的。一个口吃的人、一个爱说脏话的人，
未必希望虚拟的自己也是这样。于是有了「风格意向」（style_directives）：

  它不是规定，不是标准，是**建立在思考之前、影响侧写方向的变量**。
  它在侧写开始之前就介入——告诉引擎"学什么、不学什么、往哪个方向学"，
  而不是等侧写完了再打个补丁。优先级极高，但作用方式是引导而非篡改：
  数据里学来的风格依然是底色，意向只是让它朝本人希望的方向偏。

于是：
- 侧写判断是男性 + 身份设定"我是女性" = 说话像男性的女性
- 满嘴脏话的聊天记录 + 意向"不要说脏话" = 脏话被留在数据里，不带进人格
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path


@dataclass
class IdentityLayer:
    """身份属性 —— 可被身份设定覆盖。"""

    gender: str | None = None          # 推断的性别表达
    age_range: str | None = None       # 如 "20-25"
    self_title: str | None = None      # 自称："人家"/"老子"/"我"
    body_description: str | None = None  # 身材相关自述
    location: str | None = None
    occupation: str | None = None


@dataclass
class SocialRelation:
    """身边的一个人。称谓自称优先（"我妈"就是母亲），高频联系人算朋友。"""

    name: str                          # "我妈" / "阿茶"
    relation: str                      # 母亲 / 伴侣 / 朋友 / 同事……
    mentions: int = 1
    evidence: list[str] = field(default_factory=list)  # 出处发言


@dataclass
class KnowledgeDomain:
    """一个知识领域 + 本人真实的掌握程度。

    铁律：本人不会的，虚拟的 TA 也坦然说不知道，绝不编造。
    唯一能扩展知识的是「自我学习」——沿着本人兴趣方向持续了解新东西，
    学过的内容记进学习日志，有据可查。
    """

    domain: str                        # "科技数码" / "炒股"
    level: str = "了解"                # 擅长 / 了解 / 不会
    evidence: list[str] = field(default_factory=list)


@dataclass
class LifeLayer:
    """生活轮廓 —— 从作息和内容推断出"这个人平时怎么过日子"。"""

    life_stage: str | None = None      # 上班族/学生/自由职业（作息推断）
    occupation: str | None = None      # 具体职业线索（"我是做设计的"）
    skills: list[str] = field(default_factory=list)      # 擅长什么
    interests: list[str] = field(default_factory=list)   # 喜欢什么
    dislikes: list[str] = field(default_factory=list)    # 不喜欢什么


@dataclass
class StyleLayer:
    """行为风格 —— 从数据学习而来，可被「风格意向」引导方向（而非篡改）。"""

    catchphrases: list[str] = field(default_factory=list)   # 口头禅
    emoji_habit: str | None = None        # 高频/低频/不用，常用哪几个
    punctuation_habit: str | None = None  # 爱用句号？句尾波浪号？感叹号狂魔？
    avg_sentence_length: float | None = None
    humor_score: float | None = None      # 0-1，爱开玩笑的程度
    active_hours: list[int] = field(default_factory=list)  # 活跃时段
    #: 活跃星期（0=周一）。GriefBot 的分析里星期分布是有区分度的特征
    active_weekdays: list[int] = field(default_factory=list)
    reply_style: str | None = None        # 秒回/弧长/意念回复
    tone_keywords: list[str] = field(default_factory=list)  # 情绪基调关键词
    sample_messages: list[str] = field(default_factory=list)  # 代表性发言（few-shot 用）


@dataclass
class Persona:
    """完整人格档案 = 推断 + 身份设定覆盖 + 风格意向引导。"""

    name: str                            # 这个人怎么称呼
    identity: IdentityLayer = field(default_factory=IdentityLayer)
    style: StyleLayer = field(default_factory=StyleLayer)
    life: LifeLayer = field(default_factory=LifeLayer)
    relations: list[SocialRelation] = field(default_factory=list)
    knowledge: list[KnowledgeDomain] = field(default_factory=list)

    #: LLM 侧写归纳出的自由文本性格速写（"她是个群里气氛担当，刀子嘴豆腐心……"）。
    #: 结构化字段装不下的东西放这里，模拟器会整段放进 prompt。
    narrative: str | None = None

    #: 侧写完成日期（ISO 格式）。人是会老的——虚拟的 TA 也跟着时间走。
    profiled_at: str | None = None
    #: 侧写时的确切年龄（本人可填；填了才能随时间叠加岁数）
    age_anchor: int | None = None

    #: 自定义层 —— 人是很复杂的生物，内置的 identity/style/life 几层
    #: 装不下所有人。这里是自由扩展区：
    #: {"信仰": {"宗教": "……", "生死观": "……"}, "病情": {"……": "……"}}
    #: 每层是一个扁平 dict，模拟器会原样渲染进 prompt。
    #: 层级不是枷锁是建议：没有的层留空即可，TA 不会假装拥有。
    custom_layers: dict[str, dict] = field(default_factory=dict)

    #: 身份设定：{"gender": "女性", "age_range": "永远18岁"} ...
    #: 键对应 IdentityLayer 的字段名。值可以是陈述句也可以是愿望语气，
    #: 都会被视为强制事实。
    identity_overrides: dict[str, str] = field(default_factory=dict)

    #: 风格意向：["不要说脏话", "不要口吃", "希望说话更温柔一点"] ...
    #: 自由文本，本人对未来的自己说的话。建立在思考之前的方向变量：
    #: 侧写引擎拿着它决定学什么不学什么，模拟器拿着它校准行为。
    #: 优先级极高，但不篡改已学到的风格数据，只是引导。
    style_directives: list[str] = field(default_factory=list)

    #: 亲友的修正：["TA 不会说这么长的话", "TA 生气时其实很安静"] ...
    #: 本人不在之后，最了解 TA 的人发现的偏差写在这里，立即生效。
    #: 和意向的区别：意向是本人对自己的期望，纠正是亲友对真实的校准。
    corrections: list[str] = field(default_factory=list)

    #: 矛盾面：["life.occupation: 设计 ↔ 运营"] ...
    #: EWPA 里两个都过了阈值的竞争断言。人本来就是矛盾的——
    #: 不强行统一，两边都呈现给模拟器，让 TA 自己选择在什么情境是哪一面。
    conflicts: list[str] = field(default_factory=list)

    #: 暂停开关。非对称权限梯度：任一方都可以一票暂停，
    #: 但恢复要更多方同意——"停止容易，启动难"
    paused: bool = False
    #: 谁暂停的、什么时候（审计用）
    paused_by: str | None = None
    paused_at: str | None = None

    def apply_overrides(self) -> None:
        """身份设定压到身份层上。风格层不动——风格走意向引导，不走覆盖。"""
        for key, value in self.identity_overrides.items():
            if hasattr(self.identity, key):
                setattr(self.identity, key, value)
            else:
                raise KeyError(
                    f"身份设定 '{key}' 不存在于身份层。身份层只有："
                    f"{list(asdict(self.identity).keys())}"
                )

    def current_age(self, today: date | None = None) -> int | None:
        """按侧写时的年龄 + 流逝的年数推算现在的年龄。

        墓碑上刻着出生年份的人，在虚拟世界里继续长大/变老。
        没填 age_anchor 就返回 None —— 不知道就是不知道。
        """
        if self.age_anchor is None or not self.profiled_at:
            return None
        today = today or date.today()
        base = date.fromisoformat(self.profiled_at[:10])
        return self.age_anchor + (today - base).days // 365

    def set_layer(self, name: str, data: dict) -> None:
        """添加/更新一个自定义层。每个人的侧写都该长出自己的形状。"""
        self.custom_layers[name] = data

    def knows(self, topic: str) -> str | None:
        """本人对某个话题的掌握程度："擅长"/"了解"/"不会"，没记录返回 None。"""
        for k in self.knowledge:
            if k.domain in topic or topic in k.domain:
                return k.level
        return None

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Persona":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        p = cls(
            name=d["name"],
            identity=IdentityLayer(**d.get("identity", {})),
            style=StyleLayer(**d.get("style", {})),
            life=LifeLayer(**d.get("life", {})),
            relations=[SocialRelation(**r) for r in d.get("relations", [])],
            knowledge=[KnowledgeDomain(**k) for k in d.get("knowledge", [])],
            narrative=d.get("narrative"),
            profiled_at=d.get("profiled_at"),
            age_anchor=d.get("age_anchor"),
            custom_layers=d.get("custom_layers", {}),
            identity_overrides=d.get("identity_overrides", d.get("overrides", {})),
            style_directives=d.get("style_directives", []),
            corrections=d.get("corrections", []),
            conflicts=d.get("conflicts", []),
            paused=d.get("paused", False),
            paused_by=d.get("paused_by"),
            paused_at=d.get("paused_at"),
        )
        p.apply_overrides()
        return p
