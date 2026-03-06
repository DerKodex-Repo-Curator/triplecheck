<div align="center">

```
 ████████╗██████╗ ██╗██████╗ ██╗     ███████╗ ██████╗██╗  ██╗███████╗ ██████╗██╗  ██╗
 ╚══██╔══╝██╔══██╗██║██╔══██╗██║     ██╔════╝██╔════╝██║  ██║██╔════╝██╔════╝██║ ██╔╝
    ██║   ██████╔╝██║██████╔╝██║     █████╗  ██║     ███████║█████╗  ██║     █████╔╝
    ██║   ██╔══██╗██║██╔═══╝ ██║     ██╔══╝  ██║     ██╔══██║██╔══╝  ██║     ██╔═██╗
    ██║   ██║  ██║██║██║     ███████╗███████╗╚██████╗██║  ██║███████╗╚██████╗██║  ██╗
    ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     ╚══════╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝
```

**Three AI agents review your code — for free, on your hardware.**
<br>
**Deep review, not shallow lint. Local LLMs = unlimited passes, zero cost.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](https://github.com/raullenchai/triplecheck/pulls)

[Comparison](#-comparison) · [Quick Start](#-quick-start) · [How It Works](#-how-it-works) · [Configuration](#-configuration) · [Roadmap](#️-roadmap)

---

</div>

```
  ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐
  │          │        │          │        │          │        │          │
  │ REVIEWER │──────► │  CODER   │──────► │  TESTS   │──────► │  JUDGE   │
  │          │        │          │        │          │        │          │
  │ finds    │        │ fixes    │        │ verifies │        │ scores   │
  │ bugs     │        │ code     │        │ nothing  │        │ quality  │
  │          │        │          │        │ broke    │        │ 0 — 10   │
  └──────────┘        └──────────┘        └──────────┘        └──────────┘
       │                                       │
       │              ◄── loop until clean ──  │
       └───────────────────────────────────────┘
```

<br>

## Why triplecheck?

| | Feature | |
|:---:|---|---|
| 💰 | **$0 API cost** | Run Qwen, DeepSeek, or Llama locally via vLLM / Ollama / LM Studio |
| 🔀 | **Mix any models** | Local Qwen for reviewer + cloud Claude for judge — any combination |
| 🔧 | **Real fixes, not lint** | Produces actual code patches, applied and verified each round |
| 📦 | **Scan entire repos** | Auto-splits large codebases into review units, prioritizes by complexity |
| 🌐 | **Language agnostic** | Python, Go, Rust, TypeScript, Java, and more |
| 🧠 | **Multi-pass voting** | N review passes × different angles → vote to filter noise |
| 🔌 | **Any LLM backend** | vLLM, Ollama, LM Studio, OpenRouter, DeepSeek, OpenAI, Claude |

<br>

## 🏆 Comparison

How triplecheck stacks up against popular AI code review tools:

| | **triplecheck** | **CodeRabbit** | **PR-Agent (Qodo)** | **Sourcery** | **Ellipsis** |
|:--|:---:|:---:|:---:|:---:|:---:|
| **Open source** | ✅ MIT | ❌ SaaS | ✅ Apache-2.0 | ❌ Freemium | ❌ SaaS |
| **Run locally / self-host** | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Use your own models** | ✅ Any LLM | ❌ Fixed backend | ⚠️ OpenAI/Anthropic/custom | ❌ Fixed | ❌ Fixed |
| **$0 with local LLMs** | ✅ | ❌ $24/mo | ⚠️ Need API key | ❌ | ❌ $36/mo |
| **Auto-fix code** | ✅ Coder agent writes patches | ⚠️ One-click suggestions | ❌ Suggestions only | ❌ Suggestions only | ✅ Implements fixes |
| **Review → Fix → Test loop** | ✅ Multi-round | ❌ Single pass | ❌ Single pass | ❌ Single pass | ❌ Single pass |
| **Judge / scoring** | ✅ 0–10 verdict | ❌ | ❌ | ❌ | ❌ |
| **Multi-pass voting** | ✅ N passes, deduplicate | ❌ | ❌ | ❌ | ❌ |
| **Layered review** | ✅ arch/interface/logic/security | ❌ | ❌ | ❌ | ❌ |
| **CI test gate** | ✅ Auto-runs tests | ❌ | ❌ | ❌ | ❌ |
| **Repo-wide scan** | ✅ Auto-split + resume | ❌ PR-scoped | ❌ PR-scoped | ❌ PR-scoped | ❌ PR-scoped |
| **Tree-sitter dep graph** | ✅ Smart batching | ❌ | ❌ | ❌ | ❌ |
| **GitHub PR integration** | 🔜 Roadmap | ✅ | ✅ | ✅ | ✅ |
| **Incremental (diff-only)** | 🔜 Roadmap | ✅ | ✅ | ✅ | ✅ |
| **PR summary** | 🔜 Roadmap | ✅ | ✅ | ✅ | ✅ |
| **IDE extension** | 🔜 Roadmap | ✅ VS Code | ❌ | ✅ VS Code | ❌ |
| **In-PR chat** | ❌ | ✅ @coderabbit | ✅ /ask | ❌ | ❌ |
| **SAST integrations** | ⚠️ ruff/golint/eslint | ✅ 40+ tools | ⚠️ Limited | ❌ | ❌ |
| **Learning from feedback** | ❌ | ✅ | ❌ | ✅ | ❌ |

> **TL;DR** — triplecheck has the deepest review engine (multi-round fix loop, voting, layered review, test gate, judge scoring) and is the only tool that runs **100% free on your own hardware**. The gap is GitHub integration — coming soon.

<br>

## 🚀 Quick Start

### Install

```bash
pip install triplecheck

# Optional: smart file grouping via tree-sitter dependency graph
pip install triplecheck[graph]
```

### 3 ways to run

<table>
<tr>
<td width="33%">

**🏠 Local (free)**

```bash
# Start any OpenAI-compatible server
vllm serve Qwen/Qwen3-Coder

# Review!
triplecheck \
  --target ./my-project \
  --skip-ci
```

No API keys. No cost. Unlimited.

</td>
<td width="33%">

**☁️ Cloud API**

```bash
export DEEPSEEK_API_KEY=sk-...

triplecheck \
  --target ./my-project \
  --skip-ci
```

Fast setup, pay per token.

</td>
<td width="33%">

**🔀 Hybrid (recommended)**

```bash
# Local finds + fixes, cloud judges
triplecheck \
  --target ./my-project \
  --reviewer qwen-local \
  --coder qwen-local \
  --judge claude-opus \
  --skip-ci
```

Best quality at minimal cost.

</td>
</tr>
</table>

> **See [`examples/`](examples/) for complete config files:** [`config.local.yml`](examples/config.local.yml) · [`config.hybrid.yml`](examples/config.hybrid.yml) · [`config.cloud.yml`](examples/config.cloud.yml)

<br>

## ⚙️ How It Works

```
                          ┌─────────────────────────────────────────────────────────────┐
   Your Code              │                    Review Pipeline                           │
      │                   │                                                             │
      ▼                   │   ┌──────────┐    ┌──────────┐    ┌──────────┐              │
 ┌─────────┐              │   │ Reviewer  │───▶│  Coder   │───▶│  Tests   │──▶ Round N  │
 │ Discover│──▶ Batch ───▶│   │  (LLM)   │    │  (LLM)   │    │ (local)  │     │       │
 │  Files  │              │   └──────────┘    └──────────┘    └──────────┘     │       │
 └─────────┘              │        ▲                                │          │       │
                          │        └──────── more findings? ◀───────┘          │       │
                          │                                              converged?    │
                          │                                                    │       │
                          │                                              ┌──────────┐  │
                          │                                              │  Judge   │  │
                          │                                              │  (LLM)   │  │
                          │                                              └────┬─────┘  │
                          └───────────────────────────────────────────────────┼────────┘
                                                                             │
                                                                             ▼
                                                                     📄 Report (JSON + MD)
                                                                     Score: 8.5/10 ✅
```

### The Loop

1. **Reviewer** reads your code in batches, outputs structured findings (file, line, severity, fix suggestion)
2. **Coder** receives each finding, writes the actual fix (full file output), or rejects false positives with reasoning
3. **Tests** run automatically (pytest, go test, npm test, cargo test) — if they fail, the round stops
4. **Repeat** until no new findings or max rounds reached
5. **Judge** evaluates the entire session history and scores 0–10

### Concepts

| Concept | What it is |
|:--------|:-----------|
| **Finding** | A single issue: file, line, severity, suggested fix |
| **Batch** | A group of related files sent to the Reviewer in one call |
| **Round** | One full Reviewer → Coder → Tests cycle |
| **Session** | A complete review (multiple rounds until convergence) |
| **Unit** | A logical module in scan mode (package/directory) |
| **Scan** | Full repo review — splits into units, runs sessions, aggregates |

<br>

## 🔧 Configuration

All config lives in **`config.yml`** — three sections:

```yaml
# ── 1. Define available models ──────────────────────────────────────
models:
  qwen-local:
    provider: openai-compat
    base_url: http://localhost:8000       # vLLM / Ollama / LM Studio
    model: Qwen/Qwen3-Coder
    max_tokens: 16384                     # coder needs room for full files
    temperature: 0.1
  claude-opus:
    provider: claude-cli
    model: opus
  deepseek:
    provider: openai-compat
    base_url: https://api.deepseek.com
    model: deepseek-coder
    api_key_env: DEEPSEEK_API_KEY         # reads from environment variable

# ── 2. Assign roles → models (swap these freely) ───────────────────
assignments:
  reviewer: qwen-local                    # fast local model finds issues
  coder: qwen-local                       # fast local model writes fixes
  judge: claude-opus                      # strong model scores quality

# ── 3. Pipeline behavior ───────────────────────────────────────────
pipeline:
  max_rounds: 4                           # max review-fix iterations
  batch_max_lines: 800                    # lines per review batch
  severity_threshold: warning             # error | warning | suggestion
  auto_style_fix: true                    # run ruff/black after fixes
```

### Providers

| Provider | Config key | Compatible with |
|:---------|:-----------|:----------------|
| **OpenAI-compatible** | `openai-compat` | vLLM, Ollama, LM Studio, DeepSeek, OpenRouter, OpenAI, any `/v1/chat/completions` |
| **Claude CLI** | `claude-cli` | Claude Opus, Sonnet, Haiku via `claude` CLI |
| **Codex CLI** | `codex-cli` | OpenAI Codex via `codex` CLI |

<br>

## 📦 Scan Mode

Review entire repositories — triplecheck auto-splits into logical units:

```bash
# Preview the plan (instant, no LLM calls)
triplecheck --target ~/work/big-repo --scan --plan-only --include "**/*.go"

# Review top 5 most complex modules
triplecheck --target ~/work/big-repo --scan --max-units 5 --skip-ci \
  --include "**/*.go" --exclude "vendor/*"

# Resume a crashed scan
triplecheck --target ~/work/big-repo --scan --resume <scan_id> --skip-ci
```

<br>

## 🎯 Review Modes

Three mutually exclusive strategies — pick one:

<table>
<tr>
<th width="33%">Single Pass (default)</th>
<th width="33%">Multi-Pass + Vote</th>
<th width="33%">Layered Review</th>
</tr>
<tr>
<td>

One pass. Fast.

```yaml
pipeline:
  review_passes: 1
```

Best for small projects.

</td>
<td>

N passes × different angles.
Findings voted on. Noise filtered.

```yaml
pipeline:
  review_passes: 3
  review_min_votes: 2
  only_high_confidence: true
```

Best with **free local models** — run 5 passes, let votes filter noise.

</td>
<td>

Each layer sees only relevant context. Non-overlapping coverage.

```yaml
pipeline:
  review_layers:
    - architecture
    - interface
    - logic
    - security
```

Best for **large codebases**.

</td>
</tr>
</table>

### Stackable Enhancements

Enable on top of any review mode:

| | Feature | Config | What it does |
|:---:|:--------|:-------|:-------------|
| 🔍 | **Static Analysis** | `static_analysis: true` | Pre-screens with ruff / golint / eslint |
| 🧠 | **Cross-Round Knowledge** | `knowledge_accumulation: true` | Extracts recurring patterns → injects into next round |
| 🌳 | **Smart Grouping** | `smart_grouping: true` | Tree-sitter dep graph batches related files together |

<br>

## 🤖 Supported Models

| Model | Provider | Speed | Quality | Notes |
|:------|:---------|:-----:|:-------:|:------|
| **Qwen3-Coder** | openai-compat | ⚡⚡⚡ | ★★★★ | Best free option. Set `max_tokens ≥ 16384`. |
| **DeepSeek Coder** | openai-compat | ⚡⚡⚡ | ★★★★ | Cloud API, very cheap |
| **Llama 3.3 70B** | openai-compat | ⚡⚡ | ★★★ | Needs ~40GB VRAM |
| **Claude Opus** | claude-cli | ⚡ | ★★★★★ | Best as judge in hybrid setups |
| **Claude Sonnet** | claude-cli | ⚡⚡ | ★★★★ | Good all-rounder |
| **GPT-4o** | openai-compat | ⚡⚡ | ★★★★ | Via OpenAI or OpenRouter |

> **Tip:** Any model that serves `/v1/chat/completions` works. The table above is just what we've tested.

<br>

## 💡 Local LLM Tips

| Tip | Details |
|:----|:--------|
| **Recommended model** | Qwen3-Coder or DeepSeek-Coder for reviewer/coder roles |
| **Token budget** | Set `max_tokens ≥ 16384` for coder — it outputs full file contents |
| **Thinking tags** | If your model emits `<think>...</think>`, triplecheck auto-strips them |
| **NL fallback** | If JSON parsing fails, findings are extracted from natural language |
| **vLLM flags** | `--max-model-len 32768 --enable-prefix-caching` for best throughput |

<br>

## 📋 CLI Reference

```
triplecheck [OPTIONS]
```

| Flag | Description |
|:-----|:------------|
| `--target PATH` | Project directory to review **(required)** |
| `--config PATH` | Config file path (default: `./config.yml`) |
| `--reviewer MODEL` | Override reviewer model |
| `--coder MODEL` | Override coder model |
| `--judge MODEL` | Override judge model |
| `--max-rounds N` | Max review rounds |
| `--include PATTERN` | File glob include (repeatable) |
| `--exclude PATTERN` | File glob exclude (repeatable) |
| `--skip-tests` | Exclude test files from review |
| `--ci-cmd COMMAND` | Custom test command |
| `--skip-ci` | Skip test gate entirely |
| `--batch-max-lines N` | Max lines per review batch |
| `--output PATH` | Report output directory (default: `./reports/`) |
| `--scan` | Split repo into units and review each |
| `--plan-only` | Show scan plan only, no LLM calls |
| `--max-units N` | Review top N units by priority |
| `--resume SCAN_ID` | Resume a previous scan |

<br>

## 📄 Output

Reports are saved to `./reports/`:

| File | Contents |
|:-----|:---------|
| `<session_id>.json` | Full session state — all rounds, findings, fixes, verdict |
| `<session_id>.md` | Human-readable report with findings table, fixes, test results, judge verdict |
| `scan_<id>.json` | All unit sessions combined (scan mode) |
| `scan_<id>.md` | Overview table, per-unit summaries, aggregate score (scan mode) |

<br>

## 🔌 Adding a Provider

```python
# triplecheck/providers/my_provider.py
from triplecheck.providers.base import BaseProvider

class MyProvider(BaseProvider):
    def review(self, files, prompt, **kwargs):
        ...  # → list[Finding]

    def fix(self, file, findings, prompt, **kwargs):
        ...  # → FixResult

    def judge(self, session, prompt, **kwargs):
        ...  # → Verdict
```

Then register in `triplecheck/roles.py` → `PROVIDER_MAP` and add model entries in `config.yml`.

<br>

## 🗺️ Roadmap

### P0 — Next Up

- [ ] **GitHub PR integration** — GitHub Action + post review comments via `gh api`, line-by-line annotations
- [ ] **Incremental diff-only review** — parse `git diff`, send only changed lines + context to LLM (saves tokens, more precise)
- [ ] **PR summary / walkthrough** — auto-generate a changelog-style summary for each review session

### P1 — On Deck

- [ ] **GitHub Action template** — drop-in `.github/workflows/triplecheck.yml` for any repo
- [ ] **SARIF output** — `--format sarif` for GitHub Code Scanning / Security tab integration
- [ ] **Repo-level config** — `.triplecheck.yml` auto-discovered in repo root
- [ ] **Ignore rules** — `.triplecheck-ignore` to suppress known false positives by pattern

### P2 — Future

- [ ] **VS Code extension** — trigger review from IDE, show findings inline
- [ ] **Web report viewer** — interactive HTML report with filtering and navigation
- [ ] **GitLab / Bitbucket support** — platform-agnostic PR integration
- [ ] **Semgrep integration** — custom SAST rules alongside LLM review
- [ ] **Learning from feedback** — track dismissed findings, auto-suppress recurring false positives

> Have an idea? [Open an issue](https://github.com/raullenchai/triplecheck/issues) or send a PR.

<br>

---

<div align="center">

**Built for developers who want AI code review without the invoice.**

[Get Started](#-quick-start) · [Report Bug](https://github.com/raullenchai/triplecheck/issues) · [Request Feature](https://github.com/raullenchai/triplecheck/issues)

</div>
