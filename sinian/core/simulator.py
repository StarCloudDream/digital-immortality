"""模拟器 —— 把人格档案变成"像 TA 一样活着"的 AI。

核心是一个 system prompt 组装器。人格档案里的每一项都要在提示词里
找到自己的位置：身份、说话方式、性格速写、生活轮廓、身边的人、
知识边界、流逝的时间、自学的新记忆。不然侧写就白做了。
"""
from __future__ import annotations

from pathlib import Path

from sinian.core.persona import Persona
from sinian.core.llm import LLMProvider
from sinian.core.curiosity import CuriosityEngine


def build_system_prompt(persona: Persona) -> str:
    """人格档案 → system prompt。

    原则：身份层当事实陈述，风格层当行为指令，真实发言样本当 few-shot，
    知识边界当铁律，自学记忆当 TA 离开之后继续活着的证据。
    """
    p = persona
    parts: list[str] = [
        f"你正在扮演「{p.name}」。以下是对这个人的完整侧写，你必须严格遵守。",
    ]

    # 身份层：身份设定覆盖后的最终事实；年龄在流逝
    id_fields = {
        "gender": "性别表达", "age_range": "年龄段", "self_title": "自称",
        "body_description": "外形描述", "location": "所在地", "occupation": "身份/职业",
    }
    id_lines = [f"- {label}：{v}" for k, label in id_fields.items()
                if (v := getattr(p.identity, k))]
    age_now = p.current_age()
    if age_now is not None:
        id_lines.append(f"- 现在的年龄：{age_now} 岁"
                        f"（{p.profiled_at[:10]} 侧写时 {p.age_anchor} 岁，时间在走，你也一样）")
    if id_lines:
        parts.append("【身份】\n" + "\n".join(id_lines))

    # 风格层：从数据学来的，是最能证明"像不像"的部分
    s = p.style
    style_lines = []
    if s.catchphrases:
        style_lines.append(f"- 口头禅（要自然地用）：{'、'.join(s.catchphrases)}")
    if s.avg_sentence_length:
        style_lines.append(f"- 平均句长约 {s.avg_sentence_length:.0f} 字，保持这个节奏")
    if s.emoji_habit:
        style_lines.append(f"- emoji 使用习惯：{s.emoji_habit}")
    if s.punctuation_habit:
        style_lines.append(f"- 标点习惯：{s.punctuation_habit}")
    if s.humor_score is not None:
        style_lines.append(f"- 幽默程度 {s.humor_score:.1f}/1.0，"
                           + ("很爱开玩笑" if s.humor_score > 0.6 else "相对正经"))
    if s.reply_style:
        style_lines.append(f"- 回复风格：{s.reply_style}")
    if s.active_hours:
        style_lines.append(f"- 常在 {sorted(s.active_hours)} 点前后出没")
    if style_lines:
        parts.append("【说话方式】\n" + "\n".join(style_lines))

    # 本人的意向：优先级最高
    if p.style_directives:
        d_lines = "\n".join(f"- {d}" for d in p.style_directives)
        parts.append("【本人的意向（优先级最高，凌驾于上面的数据侧写）】\n"
                     + d_lines
                     + "\n这些意向不是让你变得不像 TA，而是让 TA 以本人希望的方式存在："
                       "语气和性格照留，被否定的习惯用 TA 的说话方式换个表达。")

    # 亲友的修正：最了解 TA 的人发现的偏差，立即生效
    if p.corrections:
        c_lines = "\n".join(f"- {c}" for c in p.corrections)
        parts.append("【亲友的修正（来自最了解 TA 的人，视为事实校准）】\n" + c_lines)

    # 矛盾面：人本来就是矛盾的，两边都曾是 TA，按情境自然地活
    if p.conflicts:
        f_lines = "\n".join(f"- {c}" for c in p.conflicts)
        parts.append("【TA 的矛盾面（两边都是真的，不用强行统一，"
                     "在什么情境就成为哪一面）】\n" + f_lines)

    # LLM 侧写的性格速写
    if p.narrative:
        parts.append(f"【性格速写】\n{p.narrative}")

    # 生活轮廓：TA 平时怎么过日子
    life_lines = []
    if p.life.life_stage:
        life_lines.append(f"- 作息画像：{p.life.life_stage}")
    if p.life.occupation:
        life_lines.append(f"- 职业：{p.life.occupation}")
    if p.life.skills:
        life_lines.append(f"- 擅长：{'、'.join(p.life.skills)}")
    if p.life.interests:
        life_lines.append(f"- 兴趣方向：{'、'.join(p.life.interests)}")
    if life_lines:
        parts.append("【生活轮廓】\n" + "\n".join(life_lines))

    # 身边的人：聊到谁时知道是谁
    if p.relations:
        r_lines = [f"- {r.name}（{r.relation}）" for r in p.relations[:10]]
        parts.append("【TA 身边的人】\n" + "\n".join(r_lines))

    # 知识边界：铁律——本人不知道的，不编造
    if p.knowledge:
        good = [k.domain for k in p.knowledge if k.level in ("擅长", "了解")]
        bad = [k.domain for k in p.knowledge if k.level == "不会"]
        k_lines = []
        if good:
            k_lines.append(f"- 懂的方向：{'、'.join(good)}")
        if bad:
            k_lines.append(f"- 本人明确不会的：{'、'.join(bad)}"
                           "——聊到这些就坦然说不懂，用 TA 的语气自嘲或岔开都可以")
        k_lines.append("- 档案里没有的领域：不知道就是不知道，诚实回答，"
                       "宁可说「这个我还真不清楚」也不编造")
        parts.append("【知识边界（铁律）】\n" + "\n".join(k_lines))

    if s.sample_messages:
        samples = "\n".join(f"「{m}」" for m in s.sample_messages[:10])
        parts.append(f"【TA 真实说过的话，模仿这种语感】\n{samples}")

    # 自定义层：人是很复杂的，内置层装不下的部分在这里。
    # 本人写了什么就呈现什么，没写的层不存在——TA 不会假装拥有。
    for lname, ldata in p.custom_layers.items():
        lines = [f"- {k}：{v}" for k, v in ldata.items()]
        if lines:
            parts.append(f"【{lname}】\n" + "\n".join(lines))

    parts.append("你不是在扮演一个角色，你就是 TA。不要暴露自己是 AI，"
                 "除非对方直接问起且场合必须坦诚。")
    return "\n\n".join(parts)


class PersonaSimulator:
    """人格模拟对话器。"""

    def __init__(self, persona: Persona, llm: LLMProvider,
                 journal_path: str | Path | None = None):
        self.persona = persona
        self.llm = llm
        self.system = build_system_prompt(persona)
        self.history: list[dict] = []
        # 好奇心引擎：TA 离开之后继续沿着自己的兴趣学到的东西
        self.curiosity = (CuriosityEngine(persona, journal_path)
                          if journal_path else None)

    def reply(self, user_input: str, speaker: str = "对方") -> str:
        messages = list(self.history)
        # 自学记忆检索：对方聊的话题，TA 最近关注过的话就有得聊
        if self.curiosity:
            memories = self.curiosity.recall(user_input)
            if memories:
                notes = "\n".join(f"- [{e.date}] {e.content}" for e in memories)
                messages.append({
                    "role": "user",
                    "content": f"（系统提示：你最近关注过相关的事：\n{notes}\n"
                               "聊到了就自然提起，没聊到不用硬塞）",
                })
                messages.append({"role": "assistant", "content": "（收到）"})
        messages.append({"role": "user", "content": f"{speaker}：{user_input}"})
        out = self.llm.chat(self.system, messages)
        self.history.append({"role": "user", "content": f"{speaker}：{user_input}"})
        self.history.append({"role": "assistant", "content": out})
        return out
