"""侧写引擎 —— 从聊天记录里把"这个人"挖出来。

核心思路：以"被侧写者自己说的话"为锚点，抓取每条发言前后各 N 条
（默认 10，可配）的上下文。别人怎么接你的话、你怎么接别人的话，
比孤立的单句更能说明你是谁。

两条腿走路：
1. 统计特征 —— 纯代码算，不依赖 LLM，免费且稳定（口头禅/句长/活跃时段……）
2. LLM 提炼 —— 把窗口片段喂给大模型归纳性格基调（幽默感/情绪/说话方式）

「风格意向」在这里是**思考之前的方向变量**：侧写开始时就注入，
决定学什么、不学什么——而不是侧写完之后删改结果。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sinian.core.message import UnifiedMessage
from sinian.core.persona import Persona, StyleLayer


@dataclass
class ContextWindow:
    """一条自我发言 + 它的前后文，侧写的基本分析单元。"""

    anchor: UnifiedMessage                 # 被侧写者本人那条消息
    before: list[UnifiedMessage]           # 前面的 N 条
    after: list[UnifiedMessage]            # 后面的 N 条


def extract_windows(
    messages: Iterable[UnifiedMessage],
    window: int = 10,
) -> list[ContextWindow]:
    """以每条 is_self 消息为锚点切窗口。跨会话不串台。"""
    windows: list[ContextWindow] = []
    by_conv: dict[str, list[UnifiedMessage]] = {}
    for msg in messages:
        by_conv.setdefault(msg.conversation_id, []).append(msg)

    for conv_msgs in by_conv.values():
        conv_msgs.sort(key=lambda m: m.timestamp)
        for i, msg in enumerate(conv_msgs):
            if not msg.is_self or not msg.content.strip():
                continue
            windows.append(ContextWindow(
                anchor=msg,
                before=conv_msgs[max(0, i - window):i],
                after=conv_msgs[i + 1:i + 1 + window],
            ))
    return windows


class DirectiveLens:
    """把自由文本的风格意向解析成统计引擎能执行的过滤方向。

    统计引擎只能做确定性的事：脏话有词表可查、口吃有模式可匹配。
    更微妙的意向（"希望更温柔"）它做不了，原样传给 LLM 侧写和模拟器，
    由有理解能力的环节去执行 —— 每一层只消化自己能消化的部分。
    """

    #: 内置粗口词表。开源项目的底线词表，本人也可以用自己的意向扩充
    PROFANITY_POOL = [
        "妈的", "他妈的", "卧槽", "我操", "操你", "傻逼", "沙币",
        "尼玛", "草泥马", "滚你", "废物", "脑残",
    ]

    #: 口吃模式：句首或句中同一个字重复 2 次以上再接别的字（"我我我觉得"），
    #: 以及顿号/省略号分隔的重复（"我、我、我想" / "我...我..."）
    STUTTER_RUN = re.compile(r"([一-鿿])\1{1,3}(?=[一-鿿，。！？])")
    STUTTER_SPLIT = re.compile(r"([一-鿿])[、…\.]{1,3}\1[、…\.]{0,3}")

    def __init__(self, directives: list[str]):
        self.raw = directives
        joined = " ".join(directives)
        self.no_profanity = any(k in joined for k in ("脏话", "粗口", "粗话", "骂人"))
        self.no_stutter = any(k in joined for k in ("口吃", "结巴", "磕巴"))

    def is_profane(self, text: str) -> bool:
        return any(w in text for w in self.PROFANITY_POOL)

    def looks_stuttered(self, text: str) -> bool:
        # 笑声（哈哈哈）不算口吃：重复字后紧跟句尾或同样是语气词的跳过
        for m in self.STUTTER_RUN.finditer(text):
            if m.group(1) not in "哈哈嘿嘻呜嗯啊啊哦欸":
                return True
        return bool(self.STUTTER_SPLIT.search(text))

    def keep_message(self, text: str) -> bool:
        """这条发言要不要进入人格学习样本。"""
        if self.no_profanity and self.is_profane(text):
            return False
        if self.no_stutter and self.looks_stuttered(text):
            return False
        return True

    def keep_catchword(self, word: str) -> bool:
        if self.no_profanity and self.is_profane(word):
            return False
        return True


class StatisticalProfiler:
    """统计侧写：纯算法，零 LLM 成本。先把这个做扎实。"""

    #: 常见语气词/口头禅候选池，后续做成可配置
    CATCHWORD_POOL = [
        "哈哈", "笑死", "确实", "好家伙", "绝了", "草", "捏", "啊这",
        "可以的", "离谱", "绷", "乐", "芜湖", "呜呜", "诶", "嘛",
        "他妈的", "卧槽", "妈的",  # 粗口也在候选里 —— 学不学由意向决定
    ]

    def __init__(self, directives: list[str] | None = None):
        # 意向是思考之前的变量： profiler 一出生就带着它
        self.lens = DirectiveLens(directives or [])

    def profile(self, windows: list[ContextWindow]) -> StyleLayer:
        all_self_msgs = [w.anchor for w in windows]
        if not all_self_msgs:
            return StyleLayer()

        # 意向先过滤学习样本：本人不想被学走的东西，根本不进入统计
        self_msgs = [m for m in all_self_msgs if self.lens.keep_message(m.content)]
        if not self_msgs:
            self_msgs = all_self_msgs  # 兜底：全过滤光了就用原始数据，宁可学歪不能学成空白

        lengths = [len(m.content) for m in self_msgs]
        hours = Counter(m.timestamp.hour for m in self_msgs)
        weekdays = Counter(m.timestamp.weekday() for m in self_msgs)
        catchwords = Counter()
        for m in self_msgs:
            for w in self.CATCHWORD_POOL:
                if self.lens.keep_catchword(w) and w in m.content:
                    catchwords[w] += m.content.count(w)

        emoji_count = sum(len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", m.content))
                          for m in self_msgs)

        # 挑代表性发言：中等长度、含口头禅的优先，留作 few-shot 样本
        samples = sorted(
            (m.content for m in self_msgs if 5 <= len(m.content) <= 80),
            key=lambda c: -sum(w in c for w in self.CATCHWORD_POOL),
        )[:20]

        return StyleLayer(
            catchphrases=[w for w, _ in catchwords.most_common(10)],
            emoji_habit=("高频" if emoji_count > len(self_msgs) else
                         "低频" if emoji_count > 0 else "不用"),
            punctuation_habit=self._punctuation_habit(self_msgs),
            avg_sentence_length=sum(lengths) / len(lengths),
            humor_score=self._humor_score(self_msgs),
            active_hours=[h for h, _ in hours.most_common(6)],
            active_weekdays=[d for d, _ in weekdays.most_common(3)],
            reply_style=self._reply_style(windows),
            sample_messages=samples,
        )

    @staticmethod
    def _punctuation_habit(msgs: list[UnifiedMessage]) -> str | None:
        """句尾标点偏好：波浪号怪、感叹号狂魔、还是懒得不加标点。"""
        tails = Counter()
        for m in msgs:
            c = m.content.rstrip()
            if not c:
                continue
            last = c[-1]
            if last in "。！？!?~…":
                tails[last] += 1
            else:
                tails["无标点"] += 1
        if not tails:
            return None
        top, n = tails.most_common(1)[0]
        if n / len(msgs) < 0.3:
            return "句尾标点随性"
        names = {"。": "句号收尾", "！": "感叹号收尾", "！": "感叹号收尾",
                 "？": "问号收尾", "~": "句尾波浪号", "…": "省略号收尾",
                 "无标点": "句尾不加标点"}
        return names.get(top, f"句尾常用'{top}'")

    @staticmethod
    def _humor_score(msgs: list[UnifiedMessage]) -> float:
        """幽默启发分：笑声词密度 + 自嘲/玩梗痕迹。粗糙但免费，LLM 侧写会修正它。"""
        laugh = sum(1 for m in msgs if re.search(r"哈{2,}|笑死|乐|绷|草\b", m.content))
        return round(min(1.0, laugh / len(msgs) * 1.5), 2)

    @staticmethod
    def _reply_style(windows: list[ContextWindow]) -> str | None:
        """从中位回复延迟看回复节奏：秒回怪还是意念回复。"""
        gaps = []
        for w in windows:
            if not w.before:
                continue
            gap = (w.anchor.timestamp - w.before[-1].timestamp).total_seconds()
            if 0 < gap < 86400:  # 超过一天的视为新话题，不算回复
                gaps.append(gap)
        if len(gaps) < 5:
            return None
        gaps.sort()
        med = gaps[len(gaps) // 2]
        if med < 60:
            return f"秒回（中位 {med:.0f} 秒）"
        if med < 600:
            return f"正常节奏（中位 {med / 60:.0f} 分钟）"
        return f"弧较长（中位 {med / 60:.0f} 分钟才回）"


class LLMProfiler:
    """LLM 侧写：把窗口喂给大模型，归纳统计算不出来的东西（幽默/性格/身份线索）。

    风格意向在这里同样生效——写进提炼 prompt，让模型归纳时就知道
    哪些方向是本人不想要的。比如"不要口吃"会让模型忽略重复音节，
    转而去学语句背后真正的表达节奏。

    窗口可能有几万个，喂之前先按时间轴均匀采样（默认 40 段），
    早年和近期的自己都照顾到；归纳结果宽容解析后 merge 进档案。
    想省 token 就别传 llm，纯统计侧写照样能跑。
    """

    PROMPT_TEMPLATE = """以下是{count}段聊天片段，每段以【本人发言】为锚点，附前后上下文。
请归纳"本人"是一个什么样的人，输出严格的 JSON（不要输出别的）：
{{
  "gender": "性别表达推断，不确定填 null",
  "age_range": "年龄段推断，不确定填 null",
  "self_title": "自称习惯，不确定填 null",
  "humor_score": 0.0到1.0的幽默程度,
  "tone_keywords": ["情绪基调关键词", "最多5个"],
  "narrative": "一段100-200字的性格速写，中文，口语化，像朋友在介绍这个人"
}}
{directives_block}

聊天片段：
{windows_text}"""

    #: 折叠式提炼的第二段提示词：带着草稿读新一批，而不是每次从头灌
    PROMPT_TEMPLATE_FOLD = """你已经在为"本人"积累一份人格速写草稿。现在读入新的一批聊天片段，
把草稿更新得更准确。只输出完整的 JSON（格式同下，字段可以改）：
{{
  "gender": "...", "age_range": "...", "self_title": "...",
  "humor_score": 0.0-1.0,
  "tone_keywords": ["...", "最多5个"],
  "narrative": "100-200字性格速写，中文口语化"
}}

【当前草稿】
{draft}

【新的一批聊天片段】
{windows_text}

{directives_block}
输出更新后的完整 JSON："""

    def __init__(self, llm, directives: list[str] | None = None,
                 max_windows: int = 40, batch: int = 10):
        self.llm = llm  # sinian.core.llm.LLMProvider
        self.directives = directives or []
        self.max_windows = max_windows
        self.batch = batch

    def _directives_block(self) -> str:
        if not self.directives:
            return ""
        lines = "\n".join(f"- {d}" for d in self.directives)
        return ("本人对侧写有以下意向（优先级最高，归纳时必须遵循，"
                "被否定的特征不要写进结果）：\n" + lines)

    @staticmethod
    def _format_window(w: ContextWindow) -> str:
        lines = [f"{m.sender_name}：{m.content}" for m in w.before]
        lines.append(f"【本人发言】{w.anchor.sender_name}：{w.anchor.content}")
        lines += [f"{m.sender_name}：{m.content}" for m in w.after]
        return "\n".join(lines)

    def _sample(self, windows: list[ContextWindow]) -> list[ContextWindow]:
        """均匀采样：时间轴上取 max_windows 段，早年和近期的自己都照顾到。"""
        if len(windows) <= self.max_windows:
            return windows
        step = len(windows) / self.max_windows
        return [windows[int(i * step)] for i in range(self.max_windows)]

    def profile(self, windows: list[ContextWindow]) -> dict:
        """返回可直接 merge 进 Persona 的 dict；LLM 输出解析失败时返回空 dict。

        窗口多的时候分批 left-fold——
        每批带着当前草稿更新，而不是把所有窗口灌进一次调用。
        上下文不炸，早年和近期的自己也都被照顾到。
        """
        if not windows:
            return {}
        sampled = self._sample(windows)
        if len(sampled) <= self.batch:
            raw = self.llm.chat("你是一位细腻的人格侧写师。",
                                [{"role": "user", "content":
                                  self._single_prompt(sampled)}])
            return self._parse_json(raw)

        # 折叠：草稿越走越厚，但每批上下文有界
        draft: dict = {}
        for i in range(0, len(sampled), self.batch):
            batch = sampled[i:i + self.batch]
            prompt = self.PROMPT_TEMPLATE_FOLD.format(
                draft=json.dumps(draft, ensure_ascii=False) if draft else "（还没有，这是第一批）",
                windows_text="\n\n---\n\n".join(self._format_window(w) for w in batch),
                directives_block=self._directives_block(),
            )
            raw = self.llm.chat("你是一位细腻的人格侧写师。",
                                [{"role": "user", "content": prompt}])
            parsed = self._parse_json(raw)
            if parsed:
                draft = parsed  # 新草稿覆盖旧草稿（LLM 输出是全量快照）
            # 解析失败的批次跳过——宁可少一批，不能拿半成品覆盖
        return draft

    def _single_prompt(self, sampled: list[ContextWindow]) -> str:
        return self.PROMPT_TEMPLATE.format(
            count=len(sampled),
            directives_block=self._directives_block(),
            windows_text="\n\n---\n\n".join(self._format_window(w) for w in sampled),
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        """模型输出未必守规矩，宽容地找第一个 {...} 块。"""
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        try:
            import json
            d = json.loads(m.group(0))
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}


def build_persona(
    name: str,
    windows: list[ContextWindow],
    identity_overrides: dict[str, str] | None = None,
    style_directives: list[str] | None = None,
    llm=None,
    age_anchor: int | None = None,
    claim_store=None,
    # 兼容旧参数名
    overrides: dict[str, str] | None = None,
) -> Persona:
    """一键侧写：意向先注入引擎，统计打底，生活轮廓跟上，LLM 补充，
    身份设定最后盖上去。

    传入 claim_store 即开启 EWPA 增量模式：本批次证据记入断言仓库，
    生效人格 = 历史全部证据的裁决结果，而不是只看这一批。
    人格学习是漫长的过程——档案随证据成熟，不被单次蒸馏定义。
    """
    from sinian.core.life import LifeProfiler

    identity_overrides = identity_overrides or overrides
    persona = Persona(
        name=name,
        style_directives=style_directives or [],
        profiled_at=date.today().isoformat(),
        age_anchor=age_anchor,
    )

    # 从窗口还原消息流给生活侧写用（窗口覆盖了全量自我发言，上下文也在里面）
    all_msgs: list[UnifiedMessage] = []
    seen = set()
    for w in windows:
        for m in [*w.before, w.anchor, *w.after]:
            key = (m.conversation_id, m.timestamp, m.content)
            if key not in seen:
                seen.add(key)
                all_msgs.append(m)

    persona.style = StatisticalProfiler(directives=style_directives).profile(windows)
    life, relations, knowledge = LifeProfiler().profile(all_msgs, name)
    persona.life, persona.relations, persona.knowledge = life, relations, knowledge

    if llm is not None:
        llm_result = LLMProfiler(llm, directives=style_directives).profile(windows)
        _merge_llm_result(persona, llm_result)

    if claim_store is not None:
        _record_claims(claim_store, persona)
        _apply_claims(claim_store, persona)

    if identity_overrides:
        persona.identity_overrides = identity_overrides
        persona.apply_overrides()
    return persona


def _record_claims(store, persona: Persona) -> None:
    """本批次提取的事实全部转成断言入库。"""
    if persona.life.occupation:
        store.add("life.occupation", persona.life.occupation, "self_statement")
    for interest in persona.life.interests:
        store.add("life.interests", interest, "statistical")
    for skill in persona.life.skills:
        store.add("life.skills", skill, "self_statement")
    for rel in persona.relations:
        store.add("relations", f"{rel.name}={rel.relation}", "kinship",
                  rel.evidence[0] if rel.evidence else "")
    for k in persona.knowledge:
        src = "self_statement" if k.level != "了解" else "statistical"
        store.add(f"knowledge.{k.domain}", k.level, src,
                  k.evidence[0] if k.evidence else "")


def _apply_claims(store, persona: Persona) -> None:
    """用历史全部证据裁决生效值。旧我不会被删除，只会被更强的证据超越。

    多值字段（兴趣/擅长/关系/知识）按阈值并集生效——
    三个月前学的"科技数码"和今天学的"烹饪"可以共存。
    """
    occupation = store.resolve("life.occupation")
    if occupation:
        persona.life.occupation = occupation
    interests = store.resolve_all("life.interests", threshold=0.5, soft=True)
    if interests:
        persona.life.interests = interests
    skills = store.resolve_all("life.skills", threshold=0.5, soft=True)
    if skills:
        persona.life.skills = skills
    # 知识边界：跨批次合并，同一领域取最高置信的等级（"不会"证据最重）
    merged: dict[str, tuple[str, float]] = {}
    for c in store.claims:
        if c.subject.startswith("knowledge."):
            domain = c.subject[len("knowledge."):]
            cur = merged.get(domain)
            if cur is None or c.confidence > cur[1]:
                merged[domain] = (c.value, c.confidence)
    if merged:
        from sinian.core.persona import KnowledgeDomain
        persona.knowledge = [KnowledgeDomain(domain=d, level=lvl)
                             for d, (lvl, _) in merged.items()]
    # 矛盾保留：单值字段上多个值都过了阈值 → 不强行统一，呈现为矛盾面。
    # 人本来就是矛盾的（"既说做设计又说做运营"可能是转行期、可能看对象说话）。
    # 但多值字段（关系/兴趣/擅长）天生就该有多个值——小雨是朋友、我妈是母亲，
    # 那是两个人，不是人格分裂，别拿去问活人"哪个更真"。
    multi_value = {"relations", "life.interests", "life.skills"}
    from collections import defaultdict
    by_subject: dict[str, list] = defaultdict(list)
    for c in store.claims:
        if c.confidence >= 0.6:
            by_subject[c.subject].append(c)
    persona.conflicts = [
        f"{subj}：{' ↔ '.join(sorted({c.value for c in cs}))}"
        for subj, cs in by_subject.items()
        if (len({c.value for c in cs}) > 1
                and subj not in multi_value
                and not subj.startswith("knowledge."))
    ]


def _merge_llm_result(persona: Persona, result: dict) -> None:
    """LLM 侧写合并进档案：身份字段只填空缺（统计没做的），不顶掉已有值。"""
    if not result:
        return
    for key in ("gender", "age_range", "self_title"):
        if result.get(key) and getattr(persona.identity, key) is None:
            setattr(persona.identity, key, str(result[key]))
    if isinstance(result.get("humor_score"), (int, float)):
        persona.style.humor_score = round(float(result["humor_score"]), 2)
    if isinstance(result.get("tone_keywords"), list):
        persona.style.tone_keywords = [str(k) for k in result["tone_keywords"][:5]]
    if result.get("narrative"):
        persona.narrative = str(result["narrative"])
