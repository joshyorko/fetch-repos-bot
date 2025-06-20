# Robocorp RCC × OpenAI Codex Agents Guide

## AGENTS.md for Codex Agents

This project uses Robocorp RCC for environment management and automation. RCC is preinstalled in the Codex environment.

---

## Install & Build
When dependencies in `conda.yaml` change, rebuild the environment:

```bash
rcc holotree vars
```

---



## Default Run
To run the main automation task:

```bash
rcc run
```

---

## Sharded Consumer Run (CI/Automation)
To run the full producer/consumer workflow with sharding (as in `start.sh`):

```bash
./start.sh
```

---

## Best Practices
* **Freeze environments** for reproducibility with `rcc holotree export --freeze > holotree.json` and check it into the repo so Codex skips long solves.
* **Disable analytics** in CI/agent sandboxes with `rcc configure identity --do-not-track`.
* **Keep tasks idempotent**—Codex may rerun commands on retry.
* **Limit external calls**; Codex containers may not have internet unless explicitly enabled.

---

## Troubleshooting
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `No holotree environment` | Project not initialized | Run `rcc run` once to build env |
| `rcc: command not found` | PATH mis‑configuration | Ensure Codex image includes `/usr/local/bin` or add `alias rcc="/path/rcc"` |
| Test run passes locally but fails when Codex commits | Relative paths or leftover state | Use `rcc task testrun` and clean output dirs before commit |

---

## Learn More
* RCC README ([github.com](https://github.com/robocorp/rcc))
* RCC Workflow Guide ([robocorp.com](https://robocorp.com/docs/rcc/workflow))
* RCC Recipes (`task script`, etc.) ([github.com](https://github.com/robocorp/rcc/blob/master/docs/recipes.md?utm_source=chatgpt.com))
* Codex Product Announcement (May 16 2025) ([openai.com](https://openai.com/index/introducing-codex/))
* Codex CLI GitHub ([github.com](https://github.com/openai/codex?utm_source=chatgpt.com))
