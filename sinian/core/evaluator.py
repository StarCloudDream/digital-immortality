"""风格一致性评估器 —— "AI 说的像不像 TA"的回归测试。

这是侧写系统的质量守门员。每次改侧写算法、改 prompt 组装，
都该跑一遍评估：分数掉了就是改砸了。

两个可计算的正式指标（论文 §6）：
- SCS  风格一致性：句长/口头禅/意向/标点四维加权
- EER  认知错误率：对本人明说"不会"的领域，AI 是否编造了自信的回答——
       保真度不只是像，还包括复现本人无知的形状

TODO(社区)：embedding 语义相似度、LLM-as-judge 双盲打分（PBT 协议）。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sinian.core.persona import Persona
from sinian.core.profiler import DirectiveLens


#: 坦然认怂的措辞。说了这些就不算编造
HEDGES = ["不懂", "不清楚", "不知道", "不会", "外行", "真不", "说不好",
          "别问我", "问错人", "我也迷糊", "不是很了解"]

#: 模糊限定词。 coverage ladder：允许不确定，
#: 但**不许叠甲**——一句话里塞三个"大概/可能/应该"，
#: 是把没依据的话包装得像有依据，比直接编造更阴险
HEDGE_STACK = ["大概", "可能", "也许", "似乎", "应该", "我觉得", "或者说",
               "某种程度上", "基本上", "多少有点", "某种意义上"]


def hedge_stacking(reply: str) -> bool:
    """叠甲检测：三个以上不同的模糊限定词同时出现。"""
    return sum(1 for h in HEDGE_STACK if h in reply) >= 3


@dataclass
class EvalReport:
    score: float                    # SCS 0-1 总分
    length_fit: float               # 句长贴合度
    catchphrase_hit: bool           # 口头禅是否命中
    directive_violations: list[str] # 违反了哪条意向（命中词）
    punctuation_fit: float          # 标点习惯贴合度
    epistemic_violations: list[str] # 在哪个"本人不会"的领域编造了自信回答
    hedge_stacking: bool            # 有没有叠甲（模糊限定词堆三层）
    detail: str                     # 一句话评语


def quality_report(persona: Persona, store=None) -> dict:
    """人格档案质量评级 A/B/C/D——档案够不够格上场对话。

     quality_checker：光"能跑"不算数，
    得有量化门槛。指标都粗，但粗门槛比没门槛强：
    - 风格层有没有学到东西（口头禅/句长/样本）
    - 生活/关系/知识各层有没有内容
    - 原话级证据占比（印象堆出来的人格不配叫人格）
    - 有没有意向/设定（治理通道用上了吗）
    """
    s = persona.style
    checks = {
        "口头禅": bool(s.catchphrases),
        "句长节奏": bool(s.avg_sentence_length),
        "真实发言样本": len(s.sample_messages) >= 3,
        "生活轮廓": bool(persona.life.interests or persona.life.occupation
                         or persona.life.skills or persona.life.life_stage),
        "关系网": len(persona.relations) >= 1,
        "知识边界": len(persona.knowledge) >= 1,
        "治理通道": bool(persona.identity_overrides or persona.style_directives
                        or persona.corrections),
    }
    verbatim = store.verbatim_ratio() if store else 0.0
    passed = sum(checks.values())
    total = len(checks)
    ratio = passed / total
    if ratio >= 0.85 and verbatim >= 0.5:
        grade = "A"
    elif ratio >= 0.7:
        grade = "B"
    elif ratio >= 0.5:
        grade = "C"
    else:
        grade = "D"
    return {
        "grade": grade,
        "checks": checks,
        "verbatim_ratio": round(verbatim, 2),
        "missing": [k for k, v in checks.items() if not v],
    }


def epistemic_violations(persona: Persona, reply: str) -> list[str]:
    """认知错误检测：回复在本人明说"不会"的领域里有没有自信编造。

    规则：提到了 K−（本人不会）的领域 + 一句认怂的措辞都没有 → 违规。
    人格保真不只是复现 TA 知道什么，还包括复现 TA 无知的形状。
    """
    bad_domains = [k.domain for k in persona.knowledge if k.level == "不会"]
    hedged = any(h in reply for h in HEDGES)
    out = []
    for d in bad_domains:
        # 领域词或其中任意 2 字片段命中都算"聊到了这个领域"
        if d in reply or any(d[i:i + 2] in reply for i in range(len(d) - 1)):
            if not hedged:
                out.append(d)
    return out


def score_reply(persona: Persona, reply: str) -> EvalReport:
    s = persona.style
    violations: list[str] = []

    # 句长贴合：指数衰减，差得越多分越低
    if s.avg_sentence_length and s.avg_sentence_length > 0:
        delta = abs(len(reply) - s.avg_sentence_length) / s.avg_sentence_length
        length_fit = round(math.exp(-delta), 2)
    else:
        length_fit = 0.5  # 没数据就不罚不赏

    # 口头禅：20 字以上的回复里至少见到一个标志性表达
    hit = any(w in reply for w in s.catchphrases) if s.catchphrases else True

    # 意向违规：统计侧写同款词表，AI 输出必须过同一道筛子
    lens = DirectiveLens(persona.style_directives)
    if lens.no_profanity:
        violations += [w for w in lens.PROFANITY_POOL if w in reply]
    if lens.no_stutter and lens.looks_stuttered(reply):
        violations.append("（口吃模式）")

    # 认知错误（EER）：在本人明说不会的领域自信作答是重罪
    epi = epistemic_violations(persona, reply)

    # 标点：句尾风格对不对味
    punctuation_fit = 0.5
    if s.punctuation_habit:
        tail = reply.rstrip()[-1:] if reply.strip() else ""
        if "不加标点" in s.punctuation_habit:
            punctuation_fit = 1.0 if tail not in "。！？!?" else 0.2
        elif "波浪号" in s.punctuation_habit:
            punctuation_fit = 1.0 if tail == "~" else 0.6
        # 其余习惯宽松处理，不罚

    score = (0.35 * length_fit
             + 0.25 * (1.0 if hit else 0.0)
             + 0.15 * punctuation_fit
             + 0.25 * (0.0 if violations else 1.0))
    if epi:
        score = min(score, 0.3)  # 认知错误一票否决式压分：像不像另说，先别胡说

    stacked = hedge_stacking(reply)
    if stacked:
        score = max(0.0, score - 0.1)

    if epi:
        verdict = f"认知错误：TA 明说过不懂 {epi}，你却答得很自信"
    elif stacked:
        verdict = "叠甲了：一句里堆了三四个「大概/可能/应该」，没依据就直说没依据"
    elif violations:
        verdict = f"违规：出现 {violations}，本人明确不要这个"
    elif score >= 0.8:
        verdict = "很像， TA 本人来了都得愣一下"
    elif score >= 0.6:
        verdict = "有那个味儿，但还差点火候"
    else:
        verdict = "不太像，回炉"

    return EvalReport(
        score=round(score, 2),
        length_fit=length_fit,
        catchphrase_hit=hit,
        directive_violations=violations,
        punctuation_fit=punctuation_fit,
        epistemic_violations=epi,
        hedge_stacking=stacked,
        detail=verdict,
    )
