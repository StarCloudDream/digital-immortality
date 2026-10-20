"""核心链路测试：消息模型 → 窗口 → 侧写 → 意向 → 评估。

跑法：python -m pytest tests/  （没装 pytest 也能 python tests/test_core.py）
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from sinian.core.message import UnifiedMessage
from sinian.core.profiler import (
    extract_windows, StatisticalProfiler, DirectiveLens, build_persona,
)
from sinian.core.persona import Persona
from sinian.core.evaluator import score_reply
from sinian.core.simulator import build_system_prompt


def make_msg(content, is_self, minutes=0, conv="c1"):
    return UnifiedMessage(
        platform="test", conversation_id=conv,
        sender_id="me" if is_self else "other",
        sender_name="薄荷" if is_self else "朋友",
        is_self=is_self,
        timestamp=datetime(2026, 10, 1, 20, 0) + timedelta(minutes=minutes),
        content=content,
    )


def sample_messages():
    msgs = []
    for i in range(20):
        msgs.append(make_msg(f"朋友说点事{i}", False, i * 2))
        word = "卧槽" if i % 5 == 0 else "哈哈"
        msgs.append(make_msg(f"{word}，这也太离谱了吧", True, i * 2 + 1))
    return msgs


def test_windows_anchored_on_self():
    windows = extract_windows(sample_messages(), window=10)
    assert len(windows) == 20
    assert all(w.anchor.is_self for w in windows)


def test_directives_filter_profanity():
    windows = extract_windows(sample_messages())
    dirty = StatisticalProfiler().profile(windows)
    clean = StatisticalProfiler(directives=["不要说脏话"]).profile(windows)
    assert "卧槽" in dirty.catchphrases
    assert "卧槽" not in clean.catchphrases
    assert "哈哈" in clean.catchphrases  # 正常的还得在


def test_stutter_detection_but_not_laughter():
    lens = DirectiveLens(["不要口吃"])
    assert lens.looks_stuttered("我我我觉得吧")
    assert not lens.looks_stuttered("哈哈哈哈哈")  # 笑声不是口吃


def test_identity_overrides_beat_inference():
    windows = extract_windows(sample_messages())
    p = build_persona("薄荷", windows,
                      identity_overrides={"gender": "女性"},
                      style_directives=["不要说脏话"])
    assert p.identity.gender == "女性"
    assert "卧槽" not in p.style.catchphrases


def test_persona_roundtrip(tmp_path: Path = None):
    p = build_persona("薄荷", extract_windows(sample_messages()),
                      identity_overrides={"gender": "女性"})
    path = Path("/tmp/persona_test.json")
    p.save(path)
    loaded = Persona.load(path)
    assert loaded.identity.gender == "女性"
    assert loaded.style.catchphrases == p.style.catchphrases


def test_evaluator_catches_violation():
    p = build_persona("薄荷", extract_windows(sample_messages()),
                      style_directives=["不要说脏话"])
    good = score_reply(p, "哈哈，确实挺离谱的")
    bad = score_reply(p, "卧槽这也太离谱了")
    assert bad.directive_violations
    assert good.score > bad.score


def test_prompt_contains_directives():
    p = build_persona("薄荷", extract_windows(sample_messages()),
                      identity_overrides={"gender": "女性"},
                      style_directives=["不要说脏话"])
    prompt = build_system_prompt(p)
    assert "不要说脏话" in prompt
    assert "女性" in prompt


def test_life_profiler_relations_and_knowledge():
    from sinian.core.life import LifeProfiler
    msgs = [
        make_msg("我妈又催我吃饭了", True, 0),
        make_msg("刚下班，老板又让我改方案", True, 1),
        make_msg("我很擅长排版", True, 2),
        make_msg("我是真的不懂炒股", True, 3),
        make_msg("这次发布会我全程追的，芯片太猛了", True, 4),
        make_msg("我学姐想学剪辑，我教了她两招", True, 5),
    ]
    # 高频联系人
    for i in range(4):
        msgs.append(make_msg(f"阿茶说话{i}", False, 10 + i))
    life, relations, knowledge = LifeProfiler().profile(msgs, "薄荷")
    rel_map = {r.name: r.relation for r in relations}
    assert rel_map.get("我妈") == "母亲"
    assert rel_map.get("学姐") == "同学"            # 校园关系也得认
    assert rel_map.get("朋友") == "朋友（高频联系人）"
    know_map = {k.domain: k.level for k in knowledge}
    assert know_map.get("炒股") == "不会"          # 本人说了不懂，就是不会
    assert "科技数码" in life.interests            # 发布会+芯片命中
    assert life.occupation or "排版" in life.skills


def test_interest_disclaimer_only_suppresses_named_domain():
    """免责声明只按住被点名的领域，不埋整条消息的兴趣。

    "不懂理财但爱看美食视频" —— 理财丢掉，美食照常算。
    """
    from sinian.core.life import LifeProfiler
    msgs = [make_msg("我是真的不懂理财，但超爱探店吃火锅", True, 0)]
    life, _, _ = LifeProfiler().profile(msgs, "薄荷")
    assert "美食" in life.interests
    assert "理财" not in life.interests


def test_knowledge_respects_disclaimer():
    """本人说了不懂炒股，理财不该被自动标成"了解"。"""
    from sinian.core.life import LifeProfiler
    msgs = [
        make_msg("我是真的不懂炒股", True, 0),
        make_msg("最近理财话题好火啊", True, 1),
    ]
    _, _, knowledge = LifeProfiler().profile(msgs, "薄荷")
    know_map = {k.domain: k.level for k in knowledge}
    assert know_map.get("炒股") == "不会"
    assert not any(k.domain == "理财" and k.level == "了解" for k in knowledge)


def test_directions_veto_only_negative_directives():
    """只有否定意向才否决方向；正面积向（"TA最爱聊理财"）不该砍方向。"""
    from sinian.core.curiosity import CuriosityEngine
    p = Persona(name="薄荷")
    p.life.interests = ["理财", "科技数码"]
    p.style_directives = ["TA最爱聊理财"]        # 正面积向，不应否决
    assert set(CuriosityEngine(p, "/tmp/j.jsonl").directions()) == {"理财", "科技数码"}

    p.style_directives = ["别聊理财"]             # 否定意向，才否决理财
    assert CuriosityEngine(p, "/tmp/j.jsonl").directions() == ["科技数码"]


def test_age_accumulates():
    from datetime import date
    p = Persona(name="薄荷", profiled_at="2026-10-20", age_anchor=25)
    assert p.current_age(today=date(2026, 12, 1)) == 25
    assert p.current_age(today=date(2031, 1, 1)) == 29
    assert Persona(name="薄荷").current_age() is None  # 不知道就是不知道


def test_curiosity_engine_learns_along_interests():
    import tempfile, os
    from sinian.core.curiosity import CuriosityEngine, ManualJsonSource
    p = Persona(name="薄荷")
    p.life.interests = ["科技数码"]
    p.style_directives = ["别让我聊理财"]
    with tempfile.TemporaryDirectory() as td:
        news = Path(td) / "news.json"
        news.write_text(json.dumps([
            {"topic": "科技数码", "content": "某厂商发布新芯片，性能提升40%"},
            {"topic": "理财", "content": "某基金大涨"},
        ], ensure_ascii=False), encoding="utf-8")
        engine = CuriosityEngine(p, Path(td) / "journal.jsonl")
        entries = engine.learn(ManualJsonSource(news))
        assert len(entries) == 1                      # 科技学，理财不学
        assert "芯片" in entries[0].content
        recalled = engine.recall("最近芯片有什么新消息")
        assert recalled and "芯片" in recalled[0].content


def test_custom_layers_roundtrip_and_render():
    """人是很复杂的：自定义层存得进、读得出、渲染得了。"""
    p = Persona(name="薄荷")
    p.set_layer("信仰与生死观", {"态度": "死亡不是终点，被遗忘才是"})
    p.set_layer("未完成的愿望", {"清单": "去看一次极光、写完那本书"})
    path = Path("/tmp/persona_layers_test.json")
    p.save(path)
    loaded = Persona.load(path)
    assert loaded.custom_layers["信仰与生死观"]["态度"].startswith("死亡")
    prompt = build_system_prompt(loaded)
    assert "信仰与生死观" in prompt and "极光" in prompt
    # 没写的层不存在——TA 不会假装拥有
    assert "病情" not in prompt


def test_corrections_and_versioning():
    """亲友修正立即生效；版本管理存档可回滚。"""
    import tempfile
    from sinian.core.versions import PersonaVault
    with tempfile.TemporaryDirectory() as td:
        vault = PersonaVault(td)
        p1 = Persona(name="薄荷")
        p1.save(vault.live_path)
        v1 = vault.snapshot(reason="pre-profile")
        assert v1 is not None

        # 第二次侧写改了点东西
        p2 = Persona(name="薄荷", corrections=["TA 生气时其实很安静"])
        p2.save(vault.live_path)
        vault.snapshot()

        # 修正进了 prompt
        loaded = Persona.load(vault.live_path)
        assert "TA 生气时其实很安静" in build_system_prompt(loaded)

        # 回滚到 v1：修正消失；再回滚回来也成立
        vault.rollback(v1)
        assert Persona.load(vault.live_path).corrections == []
        assert len(vault.list_versions()) >= 3  # 回滚本身也存档


def test_ewpa_evidence_weighted_attributes():
    """EWPA：证据累积增强、矛盾断言竞争、低置信度不生效、跨批次增量。"""
    import tempfile
    from sinian.core.evidence import ClaimStore

    with tempfile.TemporaryDirectory() as td:
        store = ClaimStore(Path(td) / "claims.json")

        # 证据累积：单调上升、边际递减
        c = store.add("life.occupation", "设计", "statistical")   # 0.30
        prev = c.confidence
        store.add("life.occupation", "设计", "self_statement")    # 本人亲口说
        assert store.claims[0].confidence > prev
        prev = store.claims[0].confidence
        store.add("life.occupation", "设计", "self_statement")
        delta1 = store.claims[0].confidence - prev
        store.add("life.occupation", "设计", "self_statement")
        delta2 = store.claims[0].confidence - prev - delta1
        assert delta2 < delta1  # 边际递减

        # 低置信度不生效（统计单次 0.3 < τ=0.6）
        assert store.resolve("life.interests") is None
        store.add("life.interests", "科技数码", "statistical")
        assert store.resolve("life.interests") is None  # 还是不够，继续未知

        # 矛盾断言竞争：旧我有累积优势（0.994），新我需要更多证据才能超越——
        # 人格转变是渐进的，不会一句话就变天
        store.add("life.occupation", "运营", "self_statement")  # 0.80
        store.add("life.occupation", "运营", "self_statement")  # 0.96
        assert store.resolve("life.occupation") == "设计"       # 还不够
        store.add("life.occupation", "运营", "self_statement")  # 0.992
        assert store.resolve("life.occupation") == "设计"       # 仍差一点
        store.add("life.occupation", "运营", "self_statement")  # 0.9984
        assert store.resolve("life.occupation") == "运营"       # 四次自述完成超越
        assert len([c for c in store.claims if c.subject == "life.occupation"]) == 2

        # 跨批次增量：第二批数据没有职业信息，生效人格仍保留历史裁决
        store.save()
        store2 = ClaimStore(Path(td) / "claims.json")  # 重新加载=下一个批次
        assert store2.resolve("life.occupation") == "运营"


def test_conflicts_preserved_not_unified():
    """矛盾保留：两个都过阈值的竞争断言不强行统一，呈现为矛盾面。"""
    import tempfile
    from sinian.core.evidence import ClaimStore
    with tempfile.TemporaryDirectory() as td:
        store = ClaimStore(Path(td) / "claims.json")
        # 两个互斥自称都积累到高置信（人是矛盾的）
        for _ in range(3):
            store.add("life.occupation", "设计", "self_statement")
            store.add("life.occupation", "运营", "self_statement")
        windows = extract_windows(sample_messages())
        p = build_persona("薄荷", windows, claim_store=store)
        assert any("设计" in c and "运营" in c for c in p.conflicts)
        prompt = build_system_prompt(p)
        assert "矛盾面" in prompt


def test_multi_value_fields_are_not_conflicts():
    """关系/兴趣/擅长天生多值——小雨是朋友、我妈是母亲，是两个人，不是矛盾。

    这个 bug 真实存在过：矛盾检测按 subject 分组，多值字段全被报成
    "两个说法都站得住"，盲盒提问追着问"哪个更真"，活人被问懵。
    """
    import tempfile
    from sinian.core.evidence import ClaimStore
    with tempfile.TemporaryDirectory() as td:
        store = ClaimStore(Path(td) / "claims.json")
        for _ in range(3):
            store.add("relations", "小雨=朋友", "kinship", "小雨喊我开黑")
            store.add("relations", "我妈=母亲", "kinship", "我妈又催我吃饭")
        # 兴趣加四次：统计印象创建 0.3、每次重复只算 0.15
        # （0.3→0.405→0.494→0.570 才过 0.5）——提过一次的玩意儿不算兴趣，
        # 这是 EWPA 的严谨，不是 bug
        for _ in range(4):
            store.add("life.interests", "科技数码", "statistical")
            store.add("life.interests", "烹饪", "statistical")
        windows = extract_windows(sample_messages())
        p = build_persona("薄荷", windows, claim_store=store)
        # 单值字段的真矛盾照报，多值字段的一片和谐
        assert not any("relations" in c or "interests" in c for c in p.conflicts)
        assert p.life.interests and "科技数码" in p.life.interests
        assert "烹饪" in p.life.interests
        from sinian.core.inquiry import suggest_questions
        qs = suggest_questions(p, store)
        assert not any("小雨" in q["question"] for q in qs)


def test_evidence_dedup_and_gate_and_retract():
    """
    import tempfile
    from sinian.core.evidence import ClaimStore

    with tempfile.TemporaryDirectory() as td:
        store = ClaimStore(Path(td) / "claims.json")
        # 同一条证据反复出现不该把置信度刷上天
        c = store.add("life.occupation", "设计", "self_statement", "我是做设计的")
        after_first = c.confidence
        store.add("life.occupation", "设计", "self_statement", "我是做设计的")
        assert store.claims[0].confidence == after_first   # 重复证据不加持
        store.add("life.occupation", "设计", "self_statement", "我做设计做了三年")
        assert store.claims[0].confidence > after_first    # 新证据才加持

        # 印象级门控：统计推断要压倒性置信度才生效
        s2 = ClaimStore(Path(td) / "s2.json")
        s2.add("life.occupation", "猜测职业", "statistical")
        assert s2.resolve("life.occupation") is None       # 0.3 印象级，不够
        s2.add("life.occupation", "猜测职业", "self_statement")  # 原话扶正
        assert s2.resolve("life.occupation") == "猜测职业"

        # 撤回：断言留在仓库，但不再生效
        assert s2.retract("life.occupation", "猜测职业")
        assert s2.resolve("life.occupation") is None
        assert any(c.revoked for c in s2.claims)


def test_rollback_fingerprint_tamper():
    """ 的 payload_sha256：存档被改动就拒绝回滚。"""
    import tempfile
    from sinian.core.versions import PersonaVault
    with tempfile.TemporaryDirectory() as td:
        vault = PersonaVault(td)
        p = Persona(name="薄荷")
        p.save(vault.live_path)
        v = vault.snapshot()
        assert vault.verify(v)
        # 有人偷偷改了存档
        (vault.archive_dir / v).write_text('{"name": "被篡改"}', encoding="utf-8")
        assert not vault.verify(v)
        try:
            vault.rollback(v)
            raise AssertionError("被篡改的存档不该回滚成功")
        except ValueError:
            pass


def test_hedge_stacking_and_quality_grade():
    """ 的禁止叠甲 + 某开源项目 的质量门槛。"""
    from sinian.core.evaluator import score_reply, hedge_stacking, quality_report
    p = build_persona("薄荷", extract_windows(sample_messages()))
    assert hedge_stacking("大概可能应该好像是这样吧")
    assert not hedge_stacking("就是这样")
    rep = score_reply(p, "大概可能应该，我也说不好")
    assert rep.hedge_stacking
    # 空档案评级应该是 D，补上内容能升上去
    empty = Persona(name="空")
    assert quality_report(empty)["grade"] == "D"
    full = build_persona("薄荷", extract_windows(sample_messages()))
    full.life.interests = ["科技数码"]
    full.relations = [__import__("sinian.core.persona", fromlist=["SocialRelation"])
                      .SocialRelation(name="阿茶", relation="朋友")]
    assert quality_report(full)["grade"] in ("A", "B", "C")


def test_inquiry_blind_questions():
    """ 的盲盒提问五型：档案哪里糊，就反问什么。"""
    from sinian.core.inquiry import suggest_questions, format_questions
    import tempfile
    from sinian.core.evidence import ClaimStore
    with tempfile.TemporaryDirectory() as td:
        store = ClaimStore(Path(td) / "claims.json")
        store.add("life.interests", "科技数码", "statistical")  # 只有印象级 → 线头
        store.add("life.occupation", "设计", "self_statement")
        store.add("life.occupation", "运营", "self_statement")   # 断层型素材
        p = Persona(name="薄荷")
        p.style.catchphrases = ["笑死"]
        p.life.interests = ["科技数码"]
        p.conflicts = ["life.occupation：设计 ↔ 运营"]
        qs = suggest_questions(p, store)
        types = {q["type"] for q in qs}
        assert "矛盾" in types and "线头" in types and "模式" in types
        assert "断层" in types  # 两个都没到 0.9
        text = format_questions(qs)
        assert "sinian correct" in text  # 答案有入口


def test_pause_is_a_one_vote_right():
    """ 非对称权限：任一方暂停即闭口，恢复才要流程。"""
    from sinian.core.simulator import PersonaSimulator
    p = Persona(name="薄荷")
    p.paused = True
    p.paused_by = "家属"
    # 暂停的人格不调 LLM 也不开口
    class ExplodingLLM:
        def chat(self, system, messages):
            raise AssertionError("暂停了不该调 LLM")
    sim = PersonaSimulator(p, ExplodingLLM())
    out = sim.reply("在吗")
    assert "暂停" in out
    # 恢复即开
    p.paused = False
    sim2 = PersonaSimulator(p, type("L", (), {
        "chat": lambda self, s, m: "在的"})())
    assert sim2.reply("在吗") == "在的"
    # 暂停状态必须能落盘再读回来——不然暂停了个寂寞
    import tempfile
    from pathlib import Path
    p.paused, p.paused_by = True, "阿茶"
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "p.json"
        p.save(f)
        back = Persona.load(f)
    assert back.paused and back.paused_by == "阿茶"


def test_llm_profiler_fold_batches():
    """ 的折叠式累积生成：分批带着草稿更新，上下文有界。"""
    import tempfile
    from sinian.core.profiler import LLMProfiler

    calls = {"n": 0}

    class CountingLLM:
        def chat(self, system, messages):
            calls["n"] += 1
            return '{"narrative": "第%d批之后的速写"}' % calls["n"]

    # 40 条本人发言 → 40 个窗口；每批 10 → 恰好 4 次调用
    big = []
    for i in range(40):
        big.append(make_msg(f"朋友说点事{i}", False, i * 2))
        big.append(make_msg(f"哈哈，第{i}句吐槽", True, i * 2 + 1))
    windows = extract_windows(big, window=10)
    assert len(windows) == 40
    prof = LLMProfiler(CountingLLM(), max_windows=40, batch=10)
    result = prof.profile(windows)
    assert calls["n"] == 4
    assert "速写" in result.get("narrative", "")


def test_epistemic_fidelity():
    """EER 认知错误率：本人明说过不会的领域，自信作答是重罪，认怂则豁免。"""
    from sinian.core.evaluator import score_reply, epistemic_violations
    from sinian.core.persona import Persona, KnowledgeDomain
    p = Persona(name="薄荷", knowledge=[KnowledgeDomain(domain="炒股", level="不会")])
    # 自信编造 → 违规
    assert epistemic_violations(p, "炒股的话我建议你全仓买入，稳赚")
    # 坦然认怂 → 豁免
    assert not epistemic_violations(p, "炒股我是真的不懂，别问我哈哈")
    # 没聊到该领域 → 不违规
    assert not epistemic_violations(p, "今晚吃火锅不")
    # 违规会被压分到 0.3 以下
    assert score_reply(p, "炒股我建议你全仓买入").score <= 0.3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"✓ {name}")
    print("全部通过")
