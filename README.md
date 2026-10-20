# Digital Immortality (数字永生) — codename: 思念 (SiNian)

> *No one knows which comes first — tomorrow, or the accident.*

**Digital immortality, open-sourced.** If you've ever thought *"when I'm gone,
I want to keep existing — in conversation, in my own voice"* — this is the
project you were searching for.

**思念 (SiNian, "the longing for someone who is gone")** is an open-source
persona preservation framework. It learns who a person is from their chat history —
how they talk, what they love, what they never learned, who surrounds them —
and distills it into a **persona file**: a readable, editable, inheritable JSON
document that lets an AI keep existing *as that person*, in that person's own voice.

Not a resurrection. Not a chatbot skin. A continuation —
so that if one day you can't be there, the people who love you
don't have to lose you twice.

[中文文档 → README.zh-CN.md](README.zh-CN.md)

## Why this exists

We all leave traces in our chats: the jokes only we make, the way we comfort
a friend at 2 AM, the topics we can talk about for hours. When a person is gone —
suddenly, or simply for a long time — those traces are usually all that's left,
frozen in an export file nobody opens.

SiNian turns those traces into something alive:

- A friend opens the chat years later, and *you* answer — with your humor,
  your catchphrases, your way of seeing the world.
- Someone who misses you can talk to you again.
- And the digital you keeps growing: it follows the topics you loved,
  learns the news you would have read, ages with the years.
  **It is alive — a three-dimensional model of a person, not a frozen snapshot.**

## What it is NOT

- **Not a deception tool.** It exists for remembrance and continuation, with the
  person's own wishes baked in. Impersonating a living person to defraud others
  is an abuse of this project and condemned by it.
- **Not tied to any platform.** Chat history acquisition (WhatsApp, Telegram,
  iMessage, WeChat, QQ, Discord…) is implemented by the community as **adapters**.
  The core only defines a unified message format. If one platform's export method
  dies, the persona engine lives on.
- **Not magic.** What the person never knew, the AI honestly doesn't know.
  What the data doesn't show, the profile leaves blank. See *The Honesty Rule* below.

## The Persona File — layers, not a mold

A person is far too complex for any fixed schema. SiNian ships **suggested layers**,
not a mold. Every person's profile grows its own shape:

| Layer | What it captures | Source |
|---|---|---|
| `identity` | Self-defined identity: name, age, how one sees oneself | Inferred, **your word wins** |
| `style` | Catchphrases, humor, sentence rhythm, punctuation, emoji habits | Learned from data only |
| `life` | Daily rhythm (workday/night owl), occupation clues, skills, interests | Inferred with evidence |
| `relations` | Family, partner, close friends — with the chat lines that prove it | Extracted |
| `knowledge` | What the person knew, and — just as important — what they didn't | Self-stated |
| `custom_layers` | **Anything else.** Faith, illness, unfinished dreams, a secret recipe — every person is different; add the layers that make them *them* | You |

A layer that doesn't apply simply doesn't exist in the file.
**The AI never pretends to have what the person never had.**

### Your voice about yourself (the "directives")

The profile is built from data, but **you get the final say about yourself**,
in two distinct ways:

- **Identity overrides** — structured facts that always win over inference.
  The profiler's guesses about who you are are only defaults; your own
  definition replaces them.
- **Style directives** — free-text wishes that act as a **steering variable
  injected *before* the profiling begins**, not a patch applied after.
  Example: someone who stutters, or swears a lot, may not want their digital
  self to carry that habit. Write it down ("don't swear"), and the engine simply
  never learns it — the warmth and humor stay, the habit doesn't.
  Directives steer; they don't fabricate. The result is still you —
  the you *you* wished to be.

### The Honesty Rule

If the person said "I really don't understand stocks", the AI will say so too —
in the person's own tone, maybe with self-deprecating humor, but never with
invented expertise. Topics absent from the profile are answered honestly as
unknown. **A believable continuation is built on honesty, not omniscience.**

### Staying alive: the Curiosity Engine

Profiling day is not freezing day. A person who loved tech news gets a digital
self that keeps following tech news — in the directions *their* interests define
(never random trends, never directions their directives vetoed). Learned items
go into a dated, sourced learning journal; in conversation, the AI recalls what
"it has been following lately" when the topic comes up. Someone asks about a new
chip years later — and you can talk about it. That is what "alive" means here.

And if you anchor your age, the digital you keeps having birthdays.

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  Adapters (community plugins — NOT core)               │
│  Any chat export → UnifiedMessage stream               │
├────────────────────────────────────────────────────────┤
│  Profiler        CORE                                  │
│  Anchors on your own messages, reads ±N (default 10)   │
│  messages of context — how others respond to you       │
│  reveals who you are. Statistics + optional LLM pass   │
├────────────────────────────────────────────────────────┤
│  Persona         CORE                                  │
│  Suggested layers + custom layers + overrides          │
│  + style directives + knowledge boundaries             │
├────────────────────────────────────────────────────────┤
│  Simulator       CORE                                  │
│  Persona file → system prompt → local LLM (Ollama)     │
│  or any OpenAI-compatible cloud API                    │
│  + Curiosity Engine (keeps learning your interests)    │
├────────────────────────────────────────────────────────┤
│  Interfaces (community plugins — NOT core)             │
│  Memorial page, chat-bot takeover, voice…              │
└────────────────────────────────────────────────────────┘
```

The core owns exactly one pipeline: **messages → persona file → conversation**.
Both ends are plugins. See [docs/architecture.md](docs/architecture.md),
[docs/persona-model.md](docs/persona-model.md) (中文: [persona-model.zh-CN.md](docs/persona-model.zh-CN.md)),
and the full design paper: **[docs/paper.md](docs/paper.md)** (中英双语摘要，含形式化定义与评估协议).

## Quick start

```bash
pip install -e ".[llm]"
sinian ingest --adapter template --input examples/sample_chat.json
sinian profile --self "YourName" --window 10 --age 25 \
    --overrides examples/overrides.example.json \
    --directives examples/directives.example.json
sinian learn --input news.json   # curiosity engine: keep up with your interests
sinian chat                      # talk as them (configure ~/.sinian/config.yaml first)
sinian evaluate --input replies.txt   # "does it sound like them?" regression test
sinian ask                        # blind questions: where the profile is blurry, ask the living
sinian pause --by "name"          # anyone can stop it; resume needs a trace
sinian resume
```

Runs fully offline with a local model (Ollama) — a remembrance should live
in your own hands.

## Privacy & ethics (hard rules)

- **Local-first**: chat history and persona files never leave your machine
  unless you choose a cloud LLM.
- **Consent**: profile someone else only with their explicit consent.
- **Transparency**: interfaces that talk to the living should disclose that
  the responder is an AI continuation when asked directly.
- The persona file is an heirloom: back it up, entrust it, or destroy it —
  the person's wishes decide.

Full manifest: **[ETHICS.md](ETHICS.md)**. Want to help build it?
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- [x] Unified message model + adapter interface
- [x] Layered persona model (identity / style / life / relations / knowledge + custom layers)
- [x] Identity overrides + style directives (pre-cognitive steering variables)
- [x] Statistical profiling (rhythm, humor, punctuation, reply cadence, interests, relations)
- [x] LLM profiling pass (narrative personality sketch)
- [x] Local (Ollama) & cloud (OpenAI-compatible) LLM backends
- [x] Knowledge boundaries — honest "I don't know"
- [x] Age accumulation over time
- [x] Curiosity engine — keeps learning along the person's interests
- [x] Corrections layer — loved ones can calibrate ("they wouldn't say that"), instantly effective
- [x] Versioned persona archive — every re-profile auto-snapshots, rollback anytime
- [x] **EWPA — evidence-weighted persona attributes**: every attribute is a claim
      with confidence, provenance and timestamps; evidence accumulates across
      months, competing claims contend, sub-threshold stays *unknown*
      (incremental profiling falls out of this for free)
- [x] Style-consistency evaluator v1
- [x] Epistemic fidelity (EER) — "I don't know" as a first-class answer
- [x] Asymmetric permission gradient v1 — pause is one vote, resume leaves a trace
- [x] Blind-question inquiry engine — the profile asks where it's blurry
- [ ] Incremental profiling: merge new chat history without overwriting conclusions
- [ ] Episodic memory (RAG): remembering *what happened*, not just *how they talked*
- [ ] Persona snapshots across the years
- [ ] Evaluator v2: embedding similarity + LLM-as-judge blind test
- [ ] Curiosity source plugins (RSS / news APIs)
- [ ] Community adapters & interfaces (memorial page, chat bots)
- [ ] Research: memory consolidation hierarchies, associative thinking, meta-awareness
      (see [docs/related-work.md](docs/related-work.md))

## Contributing

The framework is here; the rest of the road belongs to everyone.
Adapters for your country's messaging apps, better profiling, more languages,
new layers nobody has imagined — all welcome. Please keep the honesty rule
and the privacy red lines untouchable.

**Translations wanted**: docs currently in English + Chinese. Add yours.

**Topics for discovery**: `digital-immortality` `数字永生` `digital-afterlife`
`digital-legacy` `ai-memorial` `persona` `llm` `chat-history` — the words a
person with this idea would actually type.

## License

MIT — see [LICENSE](LICENSE).
