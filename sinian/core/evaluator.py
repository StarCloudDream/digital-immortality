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


@dataclass
class EvalReport:
    score: float                    # SCS 0-1 总分
    length_fit: float               # 句长贴合度
    catchphrase_hit: bool           # 口头禅是否命中
    directive_violations: list[str] # 违反了哪条意向（命中词）
    punctuation_fit: float          # 标点习惯贴合度
    epistemic_violations: list[str] # 在哪个"本人不会"的领域编造了自信回答
    detail: str                     # 一句话评语


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

    if epi:
        verdict = f"认知错误：TA 明说过不懂 {epi}，你却答得很自信"
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
        detail=verdict,
    )
