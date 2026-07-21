# QuMail — Claude Code Implementation Kit (Team Superpos3)

This kit turns Claude Code (in Antigravity / any IDE) into a disciplined pair-programmer for building **QuMail**, your quantum-secure email client. Drop these files into an empty repo and follow the steps.

## What's in the kit

| File | Role |
|------|------|
| **CLAUDE.md** | The **project skill** — persona, goal, architecture, hard constraints, crypto contracts, ETSI endpoints, conventions. Claude reads this before every task. Put it in the **repo root**. |
| **MASTER_PROMPT.md** | The **bootstrap prompt** (PROMPT 0) that scaffolds the whole repo. Paste it first. |
| **DIRECTORY_STRUCTURE.md** | The exact folder layout + team ownership map + run order. |
| **PROMPTS.md** | **Per-module prompts** (A–I). Paste one at a time to build each module with tests. |
| **README_KIT.md** | This file. |

## How to use it (start to finish)

1. **Create an empty git repo** and copy `CLAUDE.md`, `DIRECTORY_STRUCTURE.md`, `PROMPTS.md`, `MASTER_PROMPT.md` into the root.
2. **Open the repo in Claude Code** (Antigravity). Make sure it can see `CLAUDE.md`.
3. **Paste PROMPT 0** from `MASTER_PROMPT.md`. Approve each of its 5 steps. You now have a runnable skeleton.
4. **Build modules in order** using `PROMPTS.md`:
   `core (A) → KM simulator (B) → KM client (C) → crypto (D) → keystore (E) → email (F) → API (G) → frontend (H) → integration (I)`.
   Assign by owner:
   - **Member A (Quantum & Keys):** B, C, E
   - **Member B (Security Core):** A, D, most tests
   - **Member C (App & Integration):** F, G, H, I
5. **After each module:** run the printed test command, review the diff, commit.
6. **Demo:** run simulator + backend + frontend (see DIRECTORY_STRUCTURE.md "Run order").

## Golden rules for good AI-assisted results

- **One module per session.** Long sessions drift; commit and start fresh.
- **Small diffs.** If Claude tries to write everything at once, tell it to do one file.
- **Re-anchor when it drifts:** "Re-read CLAUDE.md §4 and revise."
- **Never let it fake crypto.** If liboqs isn't installed, it must raise a clear error, not simulate PQC. (This rule is in CLAUDE.md.)
- **Secrets live in `.env`,** never in code or prompts.

## Prompt-engineering anatomy (why these prompts work)

Each prompt deliberately contains:
- **Persona** — anchors expertise ("senior full-stack + crypto engineer").
- **Goal** — one clear outcome per task.
- **Inputs/Files** — names the exact files to touch (prevents sprawl).
- **Constraints** — the non-negotiables (random IVs, one-time OTP, typed errors…).
- **Output/Format** — types + docstrings + return shapes.
- **Tests** — every task ends by proving itself with pytest.

This is the same structure as a good spec: the model does best when the goal is narrow, the constraints are explicit, and success is testable.

## Adapting later

- **Real QKD hardware:** change the KM `base_url` in `.env` — the ETSI 014 contract stays identical, so no client code changes.
- **New security level / algorithm:** add a file under `backend/app/crypto/` and a branch in `engine.py`; the interface stays stable (that's the modularity requirement paying off).
- **Suite expansion (chat/voice):** reuse `core/`, `crypto/`, `km/`, `keystore/`; add a new transport alongside `email_svc/`.
```
