# Architecture

[中文版本 → architecture.zh-CN.md](architecture.zh-CN.md)

## Layer responsibilities

| Layer | Module | Core? | Maintained by |
|---|---|---|---|
| Ingestion | `sinian/adapters/*` | ❌ plugin | Community — any platform, any export method |
| Profiling | `sinian/core/profiler.py` + `life.py` | ✅ | Core team |
| Persona | `sinian/core/persona.py` | ✅ | Core team |
| Simulation | `sinian/core/simulator.py` + `llm.py` | ✅ | Core team |
| Continuation | `sinian/core/curiosity.py` | ✅ | Core team (sources are plugins) |
| Quality | `sinian/core/evaluator.py` | ✅ | Core team |
| Evidence | `sinian/core/evidence.py` | ✅ | Core team |
| Governance | `sinian/core/versions.py` + `inquiry.py` | ✅ | Core team |
| Interfaces | (future) bots / memorial pages | ❌ plugin | Community |

The core owns exactly one pipeline: **unified messages → persona file →
simulated conversation**. Both ends are plugins: how history comes in,
and how conversations go out.

## Data flow

```
Chat history (any platform)
   │  adapter.fetch() — streaming, is_self must be correct
   ▼
UnifiedMessage stream
   │  extract_windows(window=10) — anchor on the person's own messages
   ▼
ContextWindow[]  (own message ± N context, never across conversations)
   │  StatisticalProfiler + LifeProfiler (free) → LLMProfiler (optional)
   ▼
ClaimStore — every conclusion is a claim with confidence, provenance,
   timestamps; evidence accumulates across runs, competitors contend,
   sub-threshold stays *unknown*  (incremental profiling falls out of this)
   ▼
Persona (identity / style / life / relations / knowledge / custom layers)
   │  identity_overrides applied · style_directives steered the learning
   ▼
persona.json  (readable · editable · inheritable)
   │  build_system_prompt()
   ▼
LLMProvider (Ollama local / OpenAI-compatible cloud)
   ▼
The person, talking — with a Curiosity Engine keeping them up to date
```

Around this spine, the governance layer wraps two safety rails:
`PersonaVault` fingerprints every snapshot (tampered archives refuse to
roll back), and the asymmetric permission gradient lets anyone pause the
persona with one vote while resuming leaves a trace. `inquiry.py` closes
the loop in the other direction — when the profile is blurry, it asks the
living instead of guessing.

## Key design decisions

1. **Adapters stream, never materialize**: `fetch()` yields an Iterator;
   hundreds of thousands of messages won't exhaust memory.
2. **Statistics first, LLM second**: anything countable (catchphrases, rhythm,
   active hours) never costs tokens. The LLM pass handles what statistics
   can't: narrative, temperament, nuance.
3. **Anchored context**: the unit of analysis is one of the person's own
   messages plus the ±N messages around it. How others respond to you reveals
   who you are — an isolated stream of your own lines doesn't.
4. **LLM is swappable**: a `LLMProvider` abstraction; local-first for privacy,
   OpenAI-compatible for reach. `httpx` is an optional dependency.
5. **The persona file is plain JSON**: readable, hand-editable, versionable.
   Custom layers make it extensible — people are more complex than any schema.
6. **Honesty is enforced at prompt level**: knowledge boundaries and
   "unknown is a valid answer" are written into every system prompt.
7. **The evaluator is the regression gate**: every change to profiling or
   prompt assembly must keep the "does it sound like them" score up.
8. **Every attribute is a claim, not a fact**: conclusions carry
   confidence, provenance and timestamps. Competing claims contend
   instead of being silently overwritten; below-threshold stays
   *unknown* — the profile grows like a person does, gradually.

## Open tasks for the community (by priority)

1. Episodic memory (RAG): remember *what happened*, not just *how they talked*
2. Curiosity source plugins: RSS / news APIs / scheduled fetching
   (interface defined in `curiosity.py`)
3. Persona snapshots across years (incremental profiling itself is done
   via the claim store — cross-run accumulation)
4. Evaluator v2: embedding similarity + LLM-as-judge blind test
5. Adapters for messaging apps worldwide + interface plugins
   (memorial page, chat bots, voice)
