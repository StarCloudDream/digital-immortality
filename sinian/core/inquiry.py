"""盲盒提问引擎 —— TA 记不起来的，反过来问活人。

"盲盒提问五型"。人格档案不是写完就完事的——
它该知道自己哪里是糊的，并向最了解 TA 的人发问：

- 矛盾型：档案里两个说法都站得住，问人哪个更对
- 断层型：两个证据都没到压倒性置信（转行期？），问一句"后来呢"
- 线头型：兴趣只有统计级证据（印象），问有没有具体的事
- 模式型：口头禅高频出现，问"TA 一般在什么时候这样说"
- 判断边界型：聊过很多但没有留下任何知识记录的领域，问"TA 懂这个吗"

提问不是缺陷，是人格学习的入口——把亲友的答案喂回来
（`sinian correct` / 新证据），档案就长一节。
"""
from __future__ import annotations

from datetime import date

from sinian.core.evidence import ClaimStore
from sinian.core.persona import Persona

QUESTION_LIMIT = 8


def suggest_questions(persona: Persona, store: ClaimStore) -> list[dict]:
    """生成待确认的问题清单。每条带类型、问题、相关的断言出处。"""
    questions: list[dict] = []

    # 矛盾型：档案里呈现了矛盾面
    for conflict in persona.conflicts:
        questions.append({
            "type": "矛盾",
            "question": f"档案里 {conflict} 两个说法都站得住。哪个更接近 TA？"
                        "还是分场合？（写答案：sinian correct \"……\"）",
            "ref": conflict,
        })

    # 断层型：两个值都没到压倒性置信——最可能是"正在转变"。
    # 多值字段（关系/兴趣/擅长）不参与：多个朋友不是人格断层。
    multi_value = {"relations", "life.interests", "life.skills"}
    by_subject: dict[str, list] = {}
    for c in store.claims:
        if not c.revoked:
            by_subject.setdefault(c.subject, []).append(c)
    for subj, claims in by_subject.items():
        values = {c.value for c in claims}
        top = max(c.confidence for c in claims)
        if (len(values) > 1 and 0.6 <= top < 0.9
                and subj not in multi_value
                and not subj.startswith("knowledge.")):
            questions.append({
                "type": "断层",
                "question": f"{subj} 上 TA 同时有 {sorted(values)} 两种痕迹，"
                            "但都没到能拍板的程度。后来 TA 落定在哪个？",
                "ref": subj,
            })

    # 线头型：兴趣只有印象级证据
    for c in store.claims:
        if (c.subject == "life.interests" and c.level == "impression"
                and not c.revoked):
            questions.append({
                "type": "线头",
                "question": f"侧写猜 TA 对「{c.value}」有兴趣，但只是统计出来的。"
                            "有没有具体的事能证明？（比如 TA 追过什么、为它熬过什么夜）",
                "ref": c.value,
            })
            break  # 线头问一个就够，别变成审问

    # 模式型：口头禅的适用场景
    if persona.style.catchphrases:
        top_word = persona.style.catchphrases[0]
        questions.append({
            "type": "模式",
            "question": f"TA 常说「{top_word}」。一般什么时候说？"
                        "开玩笑的时候，还是化解尴尬的时候？",
            "ref": top_word,
        })

    # 判断边界型：聊得不少但知识档案空白的领域
    covered = {k.domain for k in persona.knowledge}
    for domain in persona.life.interests:
        if domain not in covered:
            questions.append({
                "type": "判断边界",
                "question": f"TA 经常聊「{domain}」，但档案里没记 TA 对这个领域"
                            "到底懂多少。TA 是资深还是爱好者？",
                "ref": domain,
            })
            break

    return questions[:QUESTION_LIMIT]


def format_questions(questions: list[dict]) -> str:
    if not questions:
        return "没有待确认的问题——档案现在很干净（或者太干净了，也可能是太空）。"
    lines = [f"档案有 {len(questions)} 个问题想问你：", ""]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. [{q['type']}] {q['question']}")
    lines.append("")
    lines.append("答案用 sinian correct \"……\" 写进来，会立即生效。")
    return "\n".join(lines)
