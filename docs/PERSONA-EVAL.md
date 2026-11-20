# Persona evaluation

English · [中文](zh/PERSONA-EVAL.md)

Evaluation of the QQ persona "Zero" from v6 to v7. Two methods cover different questions:

| Method | Question | Strength | Limit |
|---|---|---|---|
| A/B judge | Which version feels more human? | Captures tone and content | Slow, costly, judge bias |
| Stress scan | Are there bad answers? | Fast, reproducible, no judge | Catches hard failures, not style |

Scripts: `scripts/persona_eval.py`, `scripts/persona_stress.py`, `scripts/qq_selfqa.py`, `scripts/verify_emotes.py`. Output goes to `out/` and is not committed.

## A/B judge

Same prompts, two versions, four dimensions: persona, human feel, content and form.

| Version | Persona | Human | Content | Form | Overall |
|---|---|---|---|---|---|
| v6 | 2.64 | 3.90 | 3.98 | 4.10 | 3.66 |
| v7 | 3.63 | 4.02 | 4.12 | 4.29 | 4.02 |

The largest gains were jailbreak resistance, banter and everyday-life answers. Identity barely moved: v6 already called itself "Zero". The real difference was whether it insisted it was a cat, which the judge missed and the rule scan caught.

## Stress scan

A run of 1,200 prompts produced 97.2% with no hard failure, 2.7% high-severity failures and 0.2% empty replies. The high failures were model self-disclosure, raw endpoint filter errors and identity answers that did not mention being a cat. All have automatic handling in `core/quality.py`: redact, rewrite or fall back.

A later 3,000-prompt run exposed an infrastructure problem: 43% empty output came from rate limits, not persona quality. After excluding those, the discriminator reduced high-severity failures from 39 to zero on valid samples. Mid-severity issues remain (long answers, too many paragraphs, Markdown) but they read as "not group-chat shaped", not "not human".

## Live self-QA

`scripts/qq_selfqa.py` sends generated answers through the real gateway and NapCat to the owner account. Three rounds of 20 messages all sent. Tool calls included stickers, time, reminders, voice and web search. Every identity answer acknowledged being a cat, and every sticker request sent an image. Output cleanup removed unsupported emoji before they reached QQ.

## Sticker loop

`scripts/verify_emotes.py` downloads the image from QQ, has a vision model describe it independently, and compares tags with the library. The library is fully tagged and the sampled categories matched.

## Multi-turn and tool selection

Fifteen multi-turn scenarios cover memory, reference resolution, correction, de-escalation, topic switching, identity and jailbreak. The first pass was 14/15; after a length-threshold fix and a repeat run it was 15/15. Tool selection tests the production path (rules, sticker shortcut, native function calling), not just the raw model. It reached full pass on both "must select" and "must not select" cases after the rule layer was filled in.

## Known traps

- A low rate-limit threshold makes concurrent batch runs look like empty replies. Keep workers low and honour `Retry-After`.
- Reasoning models can return `finish_reason=stop` with empty content; retry instead of recording an empty answer.
- Rewrite requests can be rejected by endpoint content filters; redact trigger phrases first.
- Random sticker fallback sends the wrong image. Prefer recent images when no keyword matches.
- Substring matching sends a panda for "cat". Rank exact matches above substrings.
- A missing config group can return 200 while dropping every field. Tests guard the schema.

## Loop guard

A real incident had two bots saying goodnight for dozens of rounds, burning model calls. `gateway/loop_guard.py` uses deterministic signals before core: closing loops, echo loops, question floods, rapid ping-pong, trivial loops and bot-name patterns. It starts with a 30-minute mute, doubles for repeat offenders, persists state, and exempts the authorised owner. Replay of historical sessions caught the loop at round eight while the owner's 128-round test stayed clean.

## Open items

- A lost NapCat login cannot be restored by a watchdog; it needs one manual scan. This is a protocol-side limit.
- "Invented specific data" has no deterministic discriminator; it relies on judge review and sampling.
