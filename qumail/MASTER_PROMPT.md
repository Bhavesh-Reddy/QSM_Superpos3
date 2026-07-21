# QuMail — Master Kickoff Prompt for Claude Code

Copy the block below into Claude Code (Antigravity / your IDE) as the very first message of a fresh session, once `CLAUDE.md` is in the repo root. It bootstraps the whole project scaffold. After it runs, use the per-module task prompts in `PROMPTS.md`.

---

## ▶ PROMPT 0 — Bootstrap the repository

```
You are working on QuMail (see CLAUDE.md in the repo root — read it fully first and follow it as the source of truth).

TASK: Scaffold the entire project structure from scratch. Do NOT implement business logic yet — create the skeleton: folders, empty/interface files with docstrings, config, and tooling so three developers can work in parallel.

Persona: senior full-stack + crypto engineer on Team Superpos3.
Goal for this task: a runnable skeleton where `pytest` collects (even if tests are trivial), the FastAPI app starts, the KM simulator starts, and the React app renders a placeholder.

Constraints:
- Match the directory structure in DIRECTORY_STRUCTURE.md exactly.
- Every module gets: an __init__.py, an interface/ABC where relevant, typed stubs with Google-style docstrings, and a matching test file with at least one placeholder test.
- Create core/interfaces.py, core/exceptions.py, core/models.py (pydantic/dataclasses) first — other modules import from these.
- Add pyproject.toml (ruff+black+pytest config), requirements.txt, .env.example, .gitignore (ignore .env, __pycache__, node_modules, dist, build, *.enc).
- Add README.md with setup + run instructions for backend, km_simulator, and frontend.
- Frontend: Vite + React + Tailwind + Electron skeleton with a single placeholder screen and an api/ client stub.
- Do not put real credentials anywhere.

Deliver in this order, pausing after each numbered step so I can review:
1. core/ (models, interfaces, exceptions) + tests
2. backend/app skeleton (FastAPI app, routers, module stubs) + tests
3. km_simulator/ skeleton (ETSI 014 endpoints returning stub data) + tests
4. frontend/ skeleton (React/Electron placeholder + api client)
5. Root tooling (pyproject.toml, requirements.txt, .env.example, .gitignore, README.md)

After each step, print the commands to verify that step works.
```

---

## Why this prompt is structured this way

- **Persona + Goal + Constraints + Order** — mirrors the CLAUDE.md skill so the model stays anchored.
- **"Pause after each step"** — keeps diffs reviewable; you approve before it moves on (critical for a first build).
- **Interfaces first** — guarantees the three members can code against stable contracts immediately.
- **Skeleton before logic** — avoids the model hallucinating a monolith; you fill modules via `PROMPTS.md`.

---

## After bootstrap: the loop

For each module, open `PROMPTS.md` and paste the matching prompt. General loop:

1. **Assign** a module prompt (one member, one module).
2. Claude restates goal + files, implements, writes tests.
3. Run tests; review diff.
4. Commit. Move to next module.

Dependency order (do M-early before M-late):
**core → M6 KM Simulator → M4 KM Client → M3 Crypto → M7 KeyStore → M5 Email → M2 API wiring → M1 GUI → integration.**
