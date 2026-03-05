# Code Review Loop

Multi-agent, model-agnostic automated code review pipeline. Three LLM roles — **Reviewer** (finds issues), **Coder** (fixes code), **Judge** (final verdict) — iterate on your codebase until convergence, then you review and merge.

```
  Your Code ──► [ Reviewer ──► Coder ──► Tests ] × N rounds ──► Judge ──► You
                   find bugs    fix bugs   verify                 score     merge
```

## How It Works

1. **Reviewer** reads your code, outputs a list of findings (bug, security, perf, etc.)
2. **Coder** receives the findings, edits the actual files on disk (or rejects with reasoning)
3. **Tests** run automatically to make sure the fix didn't break anything
4. Back to step 1 — Reviewer checks the changed files again
5. When the loop converges (no more issues, or max rounds), **Judge** scores the session
6. You get a report (JSON + Markdown), review the changes, and decide whether to merge

Each role can be any LLM — Claude, Codex, a local Qwen, DeepSeek, or anything with an OpenAI-compatible API.

## Install

```bash
cd /path/to/code-review-loop
pip install -e .
```

Requires Python 3.11+. Dependencies: `pyyaml`, `httpx`, `click`.

Optional (for tree-sitter dependency graph):
```bash
pip install -e '.[graph]'
```

## Quick Start

### Simplest usage

```bash
# Review a project — tests run automatically after each fix
code-review --target ~/work/my-project
```

This will:
- Auto-detect your test command (pytest, go test, npm test, cargo test, make test)
- Use the models configured in `config.yml`
- Save reports to `./reports/`

### Skip tests (no test suite, or testing separately)

```bash
code-review --target ~/work/my-project --skip-ci
```

### Specify a custom test command

```bash
code-review --target ~/work/my-project --ci-cmd "python -m pytest tests/ -x -q"
```

### Review specific files only

```bash
code-review --target ~/work/my-project --include "src/**/*.py" --exclude "tests/*"
```

### Use all-local models (free, unlimited)

```bash
# Requires an OpenAI-compatible server running on localhost:8000 (e.g. vLLM + Qwen)
code-review --target ~/work/my-project \
  --reviewer qwen-local --coder qwen-local --judge qwen-local
```

### Mix models per role

```bash
# Cheap local model fixes code, expensive Claude judges quality
code-review --target . \
  --reviewer qwen-local --coder qwen-local --judge claude-opus
```

### Strict mode — only fix errors, limit rounds

```bash
code-review --target . --max-rounds 2
```

## Configuration

All configuration lives in `config.yml`:

```yaml
# 1. Define available LLMs
models:
  claude-opus:
    provider: claude-cli
    model: opus
  qwen-local:
    provider: openai-compat
    base_url: http://localhost:8000
    model: qwen3.5
    max_tokens: 8192
    temperature: 0.1
  deepseek:
    provider: openai-compat
    base_url: https://api.deepseek.com
    model: deepseek-coder
    api_key_env: DEEPSEEK_API_KEY

# 2. Assign roles to models (the only part you usually change)
assignments:
  reviewer: qwen-local
  coder: qwen-local
  judge: claude-opus

# 3. Pipeline behavior
pipeline:
  max_rounds: 4              # max review-fix iterations
  batch_max_lines: 6000      # split large projects into batches
  severity_threshold: warning # only fix issues at this level or above
                              # options: error | warning | suggestion
  auto_style_fix: true        # run ruff/black after each fix round
```

### Provider types

| Provider | Config key | What it calls |
|----------|-----------|---------------|
| Claude CLI | `claude-cli` | `claude -p --model opus` (or sonnet/haiku) |
| Codex CLI | `codex-cli` | `codex --quiet --full-auto` |
| OpenAI-compatible | `openai-compat` | Any `/v1/chat/completions` endpoint (vLLM, Qwen, DeepSeek, OpenRouter, Ollama, etc.) |

### Custom prompts

Each role has a system prompt in `code_review/prompts/`. Edit them or point to your own:

```yaml
roles:
  reviewer:
    prompt_file: my_prompts/reviewer.txt
```

## Test Gate (CI)

After each fix round, the pipeline automatically runs your project's tests to catch regressions:

| Project file detected | Command run |
|----------------------|-------------|
| `pyproject.toml` or `setup.py` | `pytest` |
| `go.mod` | `go test ./...` |
| `package.json` | `npm test` |
| `Cargo.toml` | `cargo test` |
| `Makefile` | `make test` |

If tests fail, the round stops immediately — no further damage.

**Options:**
- `--skip-ci` — skip test gate entirely (useful when no test suite exists)
- `--ci-cmd "your command"` — override auto-detection with a custom command

## Review Modes

Three mutually exclusive strategies. Choose one in `config.yml`:

### A) Single Pass (default)

```yaml
pipeline:
  review_passes: 1
```

One straightforward pass over all files. Fast, good for small projects.

### B) Multi-Pass with Vote Aggregation

```yaml
pipeline:
  review_passes: 3          # run 3 passes
  review_min_votes: 2        # need 2+ passes to agree for high confidence
  only_high_confidence: true # only send high-confidence findings to coder
```

Each pass uses a different focus angle (bugs, security, error handling, performance, concurrency) and shuffles file order to reduce position bias. Findings are deduplicated and voted on — only issues flagged by multiple passes get marked "high confidence" and sent to the coder. Low-confidence findings still appear in the report for human review.

Best for: **thorough review with a free local model** — run 5 passes, let the votes filter noise.

### C) Layered Review

```yaml
pipeline:
  review_layers:
    - architecture   # only sees imports → finds circular deps, layering violations
    - interface      # only sees signatures → finds API inconsistencies
    - logic          # sees full code → finds bugs, edge cases
    - security       # sees full code + data flow → finds vulnerabilities
```

Each layer sees only the relevant context (trimmed by the tool, not by the LLM). Upper layer findings are injected into lower layers so they don't repeat. Pick any subset of layers.

Best for: **large codebases** where you want structured, non-overlapping coverage.

## Enhancements

These are independent features you can enable on top of any review mode:

### Static Analysis Pre-screening

```yaml
pipeline:
  static_analysis: true
```

Runs linters before the LLM review:
- **Python:** ruff
- **Go:** golangci-lint, go vet
- **JS/TS:** eslint

Lint findings go directly into the report (not sent to coder for fixing). The LLM reviewer is told about them so it can focus on deeper issues that linters can't catch.

Gracefully skipped if tools aren't installed.

### Cross-Round Knowledge

```yaml
pipeline:
  knowledge_accumulation: true
```

After each round, the system extracts recurring patterns from findings (e.g., "missing error check appears in 8 files"). These patterns are injected into the reviewer's prompt in the next round, so it knows what to look for.

### Smart File Grouping (Tree-sitter)

```yaml
pipeline:
  smart_grouping: true
```

Requires: `pip install -e '.[graph]'`

Uses tree-sitter to parse Go and Python files, builds a dependency graph, and batches files that call each other into the same LLM request. This way the reviewer sees related code together instead of arbitrary splits by line count.

Falls back to line-count batching if tree-sitter isn't installed.

## Full Config Reference

```yaml
pipeline:
  # Core
  max_rounds: 4
  batch_max_lines: 6000
  severity_threshold: warning  # error | warning | suggestion
  auto_style_fix: true

  # Review mode (pick one)
  review_passes: 3             # >1 enables multi-pass (default: 1)
  review_min_votes: 2          # votes needed for high confidence
  only_high_confidence: true   # filter low-confidence from coder
  review_layers: []            # non-empty enables layered review
                               # e.g. [architecture, interface, logic, security]

  # Enhancements (stackable)
  static_analysis: true        # run linters before LLM review
  knowledge_accumulation: false # accumulate patterns across rounds
  smart_grouping: false         # tree-sitter dependency batching
```

## CLI Reference

```
code-review [OPTIONS]

Options:
  --target PATH            Project directory to review (required)
  --config PATH            Config file path (default: ./config.yml)
  --reviewer MODEL_NAME    Override reviewer model
  --coder MODEL_NAME       Override coder model
  --judge MODEL_NAME       Override judge model
  --max-rounds N           Override max rounds
  --include PATTERN        File glob filter (repeatable)
  --exclude PATTERN        Exclude pattern (repeatable)
  --ci-cmd COMMAND         Custom test command (auto-detected by default)
  --skip-ci                Skip test gate entirely
  --output PATH            Output directory for reports (default: ./reports/)
  --help                   Show help
```

## Output

Reports are saved to `./reports/` (or `--output`):

- **`<session_id>.json`** — full session state (all rounds, findings, fixes, verdict)
- **`<session_id>.md`** — human-readable report:
  - Per-round findings table (with confidence when multi-pass)
  - Low-confidence findings in a separate "Human Review" section
  - Fixes applied/rejected with explanations
  - Test results per round
  - Judge verdict with category scores and recommendations

## Architecture

```
                         ┌────────────────────┐
                         │    Your Codebase    │
                         └─────────┬──────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                     Swarm Review Loop                        │
│                                                              │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐                │
│   │Reviewer │───►│  Coder  │───►│  Tests  │──► next round  │
│   │ (LLM)   │    │ (LLM)   │    │ (local) │                │
│   └─────────┘    └─────────┘    └─────────┘                │
│        │              │                                      │
│        │   converge?──┘──► YES ──►┌─────────┐               │
│        │                          │  Judge  │               │
│        │                          │ (LLM)   │               │
│        ▼                          └────┬────┘               │
│   ┌──────────┐                        │                     │
│   │ Reports  │◄───────────────────────┘                     │
│   │ JSON+MD  │                                              │
│   └──────────┘                                              │
│                                                              │
│   Review Modes (pick one):                                   │
│   A) Multi-Pass — N passes × different angles → vote        │
│   B) Layered   — architecture → interface → logic → security│
│   C) Single    — one flat pass                              │
│                                                              │
│   Enhancements (stackable):                                  │
│   + Static Analysis — linters pre-screen                    │
│   + Knowledge       — cross-round pattern accumulation      │
│   + Smart Grouping  — tree-sitter dependency batching       │
└──────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │   You review the   │
                         │   diff and merge   │
                         └────────────────────┘
```

## Adding a New Provider

1. Create `code_review/providers/my_provider.py`
2. Subclass `BaseProvider` and implement `review()`, `fix()`, `judge()`
3. Register in `code_review/roles.py` → `PROVIDER_MAP`
4. Add model entries in `config.yml` with `provider: my-provider`
