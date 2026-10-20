"""命令行入口：sinian ingest / profile / chat / learn / correct …

把一个人读进来、侧写出来、再让 TA 开口说话，全在这几个命令里了。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sinian.adapters.template import TemplateJsonAdapter
from sinian.core.message import UnifiedMessage
from sinian.core.profiler import extract_windows, build_persona
from sinian.core.persona import Persona

ADAPTERS = {a.name: a for a in [TemplateJsonAdapter]}
DATA_DIR = Path.home() / ".sinian"


def load_config() -> dict:
    """读 ~/.sinian/config.yaml，没有就返回空配置。"""
    cfg_path = DATA_DIR / "config.yaml"
    if not cfg_path.exists():
        return {}
    import yaml
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def build_llm(cfg: dict):
    """按配置造 LLMProvider；没配置或缺依赖时返回 None（走纯统计模式）。"""
    llm_cfg = (cfg or {}).get("llm") or {}
    if not llm_cfg.get("provider"):
        return None
    from sinian.core.llm import OllamaProvider, OpenAICompatibleProvider
    if llm_cfg["provider"] == "ollama":
        return OllamaProvider(
            model=llm_cfg.get("model", "qwen2.5:7b"),
            base_url=llm_cfg.get("base_url", "http://127.0.0.1:11434"),
            timeout=float(llm_cfg.get("timeout", 120)),
        )
    return OpenAICompatibleProvider(
        api_key=llm_cfg.get("api_key", ""),
        model=llm_cfg.get("model", ""),
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
        timeout=float(llm_cfg.get("timeout", 120)),
    )


def cmd_ingest(args) -> None:
    adapter = ADAPTERS[args.adapter]()
    msgs = [m.to_dict() for m in adapter.fetch(args.input)]
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "messages.json"
    out.write_text(json.dumps(msgs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"收录了 {len(msgs)} 条消息 → {out}")


def cmd_profile(args) -> None:
    raw = json.loads((DATA_DIR / "messages.json").read_text(encoding="utf-8"))
    msgs = [UnifiedMessage.from_dict(d) for d in raw]
    cfg = load_config()
    window = args.window or (cfg.get("profile") or {}).get("window", 10)
    windows = extract_windows(msgs, window=window)
    identity_overrides = {}
    if args.overrides and Path(args.overrides).exists():
        identity_overrides = json.loads(Path(args.overrides).read_text(encoding="utf-8"))
    style_directives = []
    if args.directives and Path(args.directives).exists():
        style_directives = json.loads(Path(args.directives).read_text(encoding="utf-8"))
    llm = None if args.no_llm else build_llm(cfg)
    # 旧档案先存起来再动手——改砸了还能回去找她
    from sinian.core.versions import PersonaVault
    from sinian.core.evidence import ClaimStore
    vault = PersonaVault(DATA_DIR)
    archived = vault.snapshot(reason="pre-profile")
    # 断言仓库是跨批次的：这一批的证据叠在以往所有批次上面，人格就这么慢慢长大
    store = ClaimStore(DATA_DIR / "claims.json")
    persona = build_persona(args.self_name, windows,
                            identity_overrides=identity_overrides,
                            style_directives=style_directives,
                            llm=llm,
                            age_anchor=args.age,
                            claim_store=store)
    store.save()
    out = DATA_DIR / "persona.json"
    persona.save(out)
    if archived:
        print(f"旧档案已存档：{archived}")
    print(f"侧写完成：{len(windows)} 个上下文窗口"
          f"{'（含 LLM 提炼）' if llm else '（纯统计，配了 LLM 会更准）'} → {out}")
    if persona.life.life_stage:
        print(f"作息画像：{persona.life.life_stage}")
    if persona.life.interests:
        print(f"兴趣方向：{'、'.join(persona.life.interests)}")
    if persona.relations:
        print(f"身边的人：{'、'.join(r.name for r in persona.relations[:8])}")


def cmd_chat(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    print(f"人格档案已加载：{persona.name}")
    if persona.paused:
        print(f"（这个档案处于暂停状态，{persona.paused_by or '有人'} 于 "
              f"{persona.paused_at or '早些时候'} 按了暂停。"
              f"恢复要走 sinian resume，想聊先恢复）")
        return
    llm = build_llm(load_config())
    if llm is None:
        print("(没配 LLM，先把 prompt 打出来看看像不像。"
              "配置方法：cp config.example.yaml ~/.sinian/config.yaml)\n")
        from sinian.core.simulator import build_system_prompt
        print(build_system_prompt(persona))
        return
    from sinian.core.simulator import PersonaSimulator
    sim = PersonaSimulator(persona, llm, journal_path=DATA_DIR / "journal.jsonl")
    print("开始对线吧，想撤就输入 exit\n")
    while True:
        try:
            user_in = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_in.lower() in ("exit", "quit"):
            break
        if user_in:
            print(f"{persona.name}：{sim.reply(user_in)}\n")


def cmd_evaluate(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    from sinian.core.evaluator import score_reply
    replies = Path(args.input).read_text(encoding="utf-8").splitlines()
    reports = [score_reply(persona, r) for r in replies if r.strip()]
    for r, rep in zip((r for r in replies if r.strip()), reports):
        print(f"[{rep.score:.2f}] {rep.detail}\n      「{r[:50]}」")
    if reports:
        avg = sum(r.score for r in reports) / len(reports)
        print(f"\n平均像不像指数：{avg:.2f} / 1.00")


def cmd_learn(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    from sinian.core.curiosity import CuriosityEngine, ManualJsonSource
    engine = CuriosityEngine(persona, DATA_DIR / "journal.jsonl")
    dirs = engine.directions()
    print(f"TA 的关注方向：{'、'.join(dirs) if dirs else '（还没侧写出兴趣，先跑 profile）'}")
    if not args.input:
        return
    entries = engine.learn(ManualJsonSource(args.input))
    print(f"学进了 {len(entries)} 条新消息：")
    for e in entries:
        print(f"  [{e.domain}] {e.content[:60]}")


def cmd_correct(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    persona.corrections.append(args.text)
    persona.save(DATA_DIR / "persona.json")
    print(f"修正已记录并立即生效：{args.text}")
    print(f"（累计 {len(persona.corrections)} 条修正）")


def cmd_versions(args) -> None:
    from sinian.core.versions import PersonaVault
    vault = PersonaVault(DATA_DIR)
    versions = vault.list_versions()
    if not versions:
        print("还没有历史版本（每次 profile 覆盖前会自动存档）")
        return
    print("历史版本：")
    for v in versions:
        print(f"  {v}")


def cmd_rollback(args) -> None:
    from sinian.core.versions import PersonaVault
    vault = PersonaVault(DATA_DIR)
    vault.rollback(args.version)
    print(f"已回滚到 {args.version}（回滚前的版本也已存档，随时可以回来）")


def cmd_quality(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    from sinian.core.evaluator import quality_report
    from sinian.core.evidence import ClaimStore
    rep = quality_report(persona, ClaimStore(DATA_DIR / "claims.json"))
    print(f"人格档案评级：{rep['grade']}"
          f"（原话级证据占比 {rep['verbatim_ratio']:.0%}）")
    for k, ok in rep["checks"].items():
        print(f"  {'✓' if ok else '✗'} {k}")
    if rep["missing"]:
        print(f"\n还差这些才能上场：{'、'.join(rep['missing'])}")


def cmd_retract(args) -> None:
    """撤回一条断言：本人说不算数，就真不算数。"""
    from sinian.core.evidence import ClaimStore
    store = ClaimStore(DATA_DIR / "claims.json")
    if not store.retract(args.subject, args.value):
        print(f"没找到这条断言：{args.subject} = {args.value}")
        return
    store.save()
    print(f"已撤回：{args.subject} = {args.value}"
          "（断言保留在仓库里，但不再进入人格）")


def cmd_ask(args) -> None:
    """盲盒提问：档案哪里是糊的，反问最了解 TA 的人。"""
    from sinian.core.inquiry import suggest_questions, format_questions
    from sinian.core.evidence import ClaimStore
    persona = Persona.load(DATA_DIR / "persona.json")
    questions = suggest_questions(persona, ClaimStore(DATA_DIR / "claims.json"))
    print(format_questions(questions))


def cmd_pause(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    persona.paused = True
    persona.paused_by = args.by
    persona.paused_at = __import__("datetime").date.today().isoformat()
    persona.save(DATA_DIR / "persona.json")
    print(f"已暂停（{args.by}）。任一方都能暂停，恢复要走治理流程——停止容易，启动难")


def cmd_resume(args) -> None:
    persona = Persona.load(DATA_DIR / "persona.json")
    persona.paused = False
    persona.paused_by = None
    persona.paused_at = None
    persona.save(DATA_DIR / "persona.json")
    print("已恢复。谁恢复的、为什么，请记在 issue 或留言里——恢复比暂停难，得留痕")


def cmd_claims(args) -> None:
    from sinian.core.evidence import ClaimStore
    store = ClaimStore(DATA_DIR / "claims.json")
    if not store.claims:
        print("断言仓库为空（先跑 profile）")
        return
    print(f"{'置信度':<8}{'字段':<22}{'值':<24}来源")
    for c in store.table():
        bar = "█" * int(c.confidence * 10) + "░" * (10 - int(c.confidence * 10))
        print(f"{bar} {c.confidence:.2f}  {c.subject:<20}{c.value:<22}{c.source}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="sinian", description="思念——把一个人读出来，再让 TA 开口")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="导入聊天记录")
    p.add_argument("--adapter", default="template", choices=list(ADAPTERS))
    p.add_argument("--input", required=True)
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("profile", help="生成人格侧写")
    p.add_argument("--self", dest="self_name", required=True, help="被侧写者称呼")
    p.add_argument("--window", type=int, default=None, help="前后文窗口大小，默认读配置或10条")
    p.add_argument("--overrides", help="身份设定 JSON 文件路径（强制覆盖身份层）")
    p.add_argument("--directives", help="风格意向 JSON 文件路径（影响侧写方向的变量）")
    p.add_argument("--no-llm", action="store_true", help="跳过 LLM 提炼，只跑统计侧写")
    p.add_argument("--age", type=int, default=None, help="侧写时的确切年龄（填了才能随时间叠加）")
    p.set_defaults(fn=cmd_profile)

    p = sub.add_parser("chat", help="以 TA 的人格开始对话")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("evaluate", help="评估候选回复像不像 TA（每行一条）")
    p.add_argument("--input", required=True, help="候选回复文本文件")
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("learn", help="好奇心引擎：沿 TA 的兴趣方向学新东西")
    p.add_argument("--input", help="信息源 JSON 文件（[{\"topic\":..., \"content\":...}]）")
    p.set_defaults(fn=cmd_learn)

    p = sub.add_parser("correct", help="亲友修正：TA 不会这样 → 写入立即生效")
    p.add_argument("text", help="修正内容，如：TA 生气时其实很安静")
    p.set_defaults(fn=cmd_correct)

    p = sub.add_parser("versions", help="列出人格档案历史版本")
    p.set_defaults(fn=cmd_versions)

    p = sub.add_parser("rollback", help="回滚到某个历史版本")
    p.add_argument("--version", required=True)
    p.set_defaults(fn=cmd_rollback)

    p = sub.add_parser("claims", help="查看证据断言表（人格的置信度全貌）")
    p.set_defaults(fn=cmd_claims)

    p = sub.add_parser("quality", help="人格档案质量评级 A/B/C/D")
    p.set_defaults(fn=cmd_quality)

    p = sub.add_parser("ask", help="盲盒提问：档案哪里是糊的，问活人")
    p.set_defaults(fn=cmd_ask)

    p = sub.add_parser("pause", help="暂停数字人格（任一方的一票权）")
    p.add_argument("--by", default="未署名", help="谁暂停的（审计用）")
    p.set_defaults(fn=cmd_pause)

    p = sub.add_parser("resume", help="恢复数字人格（要走流程，留痕）")
    p.set_defaults(fn=cmd_resume)

    p = sub.add_parser("retract", help="撤回一条断言（本人说不算数就不算数）")
    p.add_argument("subject", help="字段路径，如 life.occupation")
    p.add_argument("value", help="要撤回的值")
    p.set_defaults(fn=cmd_retract)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
