# The Persona Model — Design Document

[中文版本 → persona-model.zh-CN.md](persona-model.zh-CN.md)

## Layers, not a mold

No fixed schema can hold a whole person. SiNian's persona file is therefore
a set of **suggested layers plus an open extension area** — every profile
grows its own shape.

### Built-in (suggested) layers

**Identity (`identity`) — self-defined.**
How the person sees themself: name, age, identity. The profiler may infer
defaults, but these are *defaults*. The person's own word — `identity_overrides` —
always wins. Identity is a narrative, and the author of that narrative is
the person, not the data.

**Style (`style`) — learned, never fabricated.**
Catchphrases, sentence rhythm, humor density, punctuation and emoji habits,
active hours, reply cadence. This layer is evidence, woven into every message
the person ever sent. It is learned from data — but see *style directives* below:
learning can be steered.

**Life (`life`) — inferred with evidence.**
Daily rhythm (weekday-daytime silence suggests a job; all-day activity suggests
a student or freelancer; a heavy late-night share marks a night owl),
occupation self-statements, skills, interests. With fewer than 30 self-messages
the rhythm is left blank — *unknown is a valid answer*.

**Relations (`relations`) — evidence-backed.**
Kinship terms in one's own messages are hard proof ("my mom" ⇒ mother).
Frequent contacts are marked as friends. Every relation carries the original
chat lines as evidence, open to human review.

**Knowledge (`knowledge`) — the honesty boundary.**
What the person explicitly said they know, and — equally important — what they
said they *don't*. "I really don't understand stocks" is recorded as unknown.
In simulation this is a hard rule: the AI admits ignorance in the person's own
voice rather than inventing expertise. Topics absent from the file are treated
as unknown too. A believable continuation is built on honesty.

### Custom layers (`custom_layers`)

Faith, illness, unfinished dreams, a family recipe, a private philosophy —
the things that make a person *them* rarely fit a schema. `custom_layers` is a
free-form area (`dict[str, dict]`), rendered verbatim into the simulation prompt.
Write the layers that matter; skip the ones that don't. **What isn't written
simply doesn't exist — the AI never pretends to have what the person never had.**

## The person's final say: overrides & directives

Both are *the person's own voice about their future self*, and both accept
plain statements or wishes ("I hope…") — that is the natural grammar of this
project.

| | Identity overrides | Style directives |
|---|---|---|
| Form | structured `{"field": "value"}` | free text `["don't swear", …]` |
| Acts on | identity layer | style layer & learning process |
| Mechanism | hard replace, highest priority | **steering variable injected before profiling begins** |
| Timing | after inference | before learning, through simulation |

A directive is not a rule and not a standard — it is a variable that exists
*prior to thinking* and bends the direction of profiling. It decides what gets
learned and what never enters the samples. Profanity never appears in the
catchphrase list because it was never counted. Stuttered lines never become
few-shot samples. And at simulation time the directive is phrased as guidance,
not prohibition: *"keep the tone, swap the habit out in your own voice."*

Each stage digests what it can: deterministic filters (profanity lexicon,
stutter patterns) run in the statistical profiler; subtler wishes
("stay gentle") pass through to the LLM profiler and the simulation prompt,
where understanding lives.

## Time

`profiled_at` + `age_anchor` let the persona age with real time — the digital
self keeps having birthdays. Unknown age stays unknown.

## The Curiosity Engine — staying alive

Profiling day is not freezing day. Learning directions are derived from the
person's own interests and known domains — never random trends, and vetoed
topics stay vetoed. Everything learned lands in a dated, sourced journal
(`journal.jsonl`); conversation retrieves relevant entries by topic, so the
persona can talk about the world *after* profiling day. It grows — along the
paths the person would have walked.

## File format

The persona file is plain JSON (`~/.sinian/persona.json`): human-readable,
hand-editable, versionable. Treat it as an heirloom — back it up, entrust it,
or destroy it, as its owner wishes.
