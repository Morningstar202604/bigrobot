# Positioning

English · [中文](zh/COMPARISON.md)

BigRobot is a platform that takes over an existing chat account. It is not a general workflow builder, a chat front end, or a plugin marketplace.

## What it is

One process connects model APIs and protocol endpoints, and keeps permissions, approvals, audit, memory and retrieval inside the engine rather than in a prompt. The account is the centre: groups, members, files and history are first-class, and actions are bounded by policy.

## What it is not

| Not | Because |
|---|---|
| Visual workflow platform | The job is staying alive in a group, not dragging a pipeline |
| Self-hosted AI chat UI | The job is an assistant acting for a person, not another chat box |
| Ticketing system | Operator takeover is one module, not the product skeleton |
| IM framework that only replies | Replying is the start; execution needs approval and a trail |

## Where the difference shows

| Area | BigRobot |
|---|---|
| Account model | Takes over an existing account and exposes what is really there |
| Permissions | Risk tiers plus subject tiers; destructive actions require approval |
| Audit | Hash-chained records that can be verified from the console |
| No model key | Rules and retrieval still run; the group does not go silent |
| Persona | Structured cards, drift checks, reminders and long-term memory |
| Multi-account | Sessions, memory and actions isolated per bot account |
| Extension | Declarative HTTP packs and MCP; no Python plugin inside core |

## Deliberate limits

- **Platform count is small.** QQ is the deep path; adding a platform should be a declaration, not a second product.
- **No plugin marketplace.** Remote Python plugins in the core process conflict with the permission model.
- **No visual orchestration.** Configuration is the orchestration surface.
- **No feature-count race.** The moat is the boring work that keeps an account alive: memory, reminders, permissions, approvals, audit, persona consistency, loop guards and a no-key fallback.

The useful comparison is not "who has more boxes". It is "what does it cost to add one capability, one platform or one account without losing control". BigRobot is built around lowering that cost while keeping the account and its boundaries intact.
