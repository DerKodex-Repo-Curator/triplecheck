# Code Review Loop

Multi-agent, model-agnostic automated code review pipeline. Three LLM roles — **Reviewer** (finds issues), **Coder** (fixes code), **Judge** (final verdict) — iterate on your codebase until convergence, then you review and merge.

```
  Your Code ──► [ Reviewer ──► Coder ──► Tests ] × N rounds ──► Judge ──► You
                   find bugs    fix bugs   verify                 score     merge
```

## Core Concepts

### Hierarchy (small → large)

| Concept | What it is | Example |
|---------|-----------|---------|
| **Finding** | A single code issue with file, line, severity, and fix suggestion | `cli.py:475 — session.verdict may be None` |
| **Batch** | A group of related files sent to the Reviewer in one LLM call | 3 related `.go` files, ~400 lines total |
| **Round** | One full Reviewer → Coder → Tests cycle across all batches | Round 1: 95 findings → fix 7 files → Round 2: 0 findings → converged |
| **Session** | A complete review of one target (multiple rounds until convergence) | Review `consensus/` → 3 rounds → Judge scores 8.5 |
| **Unit** | A logical module in scan mode (package or directory grouping) | `iotex-core/consensus/`, `iotex-core/action/protocol/` |
| **Scan** | A full repo-level review — splits repo into units, runs a session per unit, aggregates results | Scan `iotex-core` → 30 units → 30 sessions → aggregate report |

### Three Roles

| Role | Input | Output | When called |
|------|-------|--------|-------------|
| **Reviewer** | Batch of files + system prompt | `Finding[]` — list of issues found | Every round, once per batch |
| **Coder** | Single file + its findings | `FixResult` — the entire fixed file (or rejection) | Every round, once per file with findings |
| **Judge** | Full session history (all rounds, findings, fixes) | `Verdict` — score (0-10), pass/fail/partial, recommendations | Once, after the review loop converges |

### Pipeline Flow

```
Scan Mode (--scan)
 │
 ├── Unit 1: consensus/
 │    └── Session
 │         ├── Round 1
 │         │    ├── Static Analysis ──► ruff / golint findings (informational)
 │         │    ├── Reviewer ──► Batch 1 → findings, Batch 2 → findings, ...
 │         │    ├── Coder ──► fix file A, fix file B, reject file C
 │         │    ├── Tests ──► pytest / go test (CI gate)
 │         │    └── Style ──► auto-format changed files
 │         ├── Round 2
 │         │    ├── Reviewer ──► re-review only changed files → 0 findings
 │         │    └── Converged!
 │         └── Judge ──► score 8.5, status: pass
 │
 ├── Unit 2: action/protocol/
 │    └── Session → Rounds → ...
 │
 └── Aggregate Report (merge all unit results into one report)
```

In **single-target mode** (without `--scan`), there's no unit/scan layer — it's just one session directly on the target directory.

### Supporting Concepts

| Concept | What it does |
|---------|-------------|
| **Smart Grouping** | Tree-sitter parses code, builds dependency graph, batches files that call each other together |
| **Multi-Pass Review** | Same batch reviewed N times with different focus angles; findings are voted on and deduplicated |
| **Layered Review** | Specialized review passes (architecture → interface → logic → security), each seeing only relevant context |
| **Knowledge Accumulator** | Extracts recurring patterns across batches ("this codebase often misses null checks"), injects into next round's prompt |
| **Static Analysis** | Runs linters (ruff, golint, eslint) before LLM review; findings go to report, reviewer is told to focus on deeper issues |
| **Scan Progress** | Checkpoint file for scan mode — if a scan crashes mid-way, `--resume <scan_id>` continues from where it left off |

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
# Cheap local model finds and fixes, expensive Claude judges quality
code-review --target . \
  --reviewer qwen-local --coder qwen-local --judge claude-opus
```

### Scan a large repo

```bash
# See how the repo will be split (instant, no LLM calls)
code-review --target ~/work/iotex-core --scan --plan-only --include "**/*.go"

# Review top 5 most important modules
code-review --target ~/work/iotex-core --scan --max-units 5 --skip-ci \
  --include "**/*.go" --exclude "vendor/*" --skip-tests

# Full scan
code-review --target ~/work/iotex-core --scan --skip-ci \
  --include "**/*.go" --exclude "vendor/*" --skip-tests
```

### Resume a crashed scan

```bash
# Find the scan ID from the previous output or reports/ directory
code-review --target ~/work/iotex-core --scan --resume abc123def456 --skip-ci
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
  --skip-tests             Exclude test files and directories from review
  --ci-cmd COMMAND         Custom test command (auto-detected by default)
  --skip-ci                Skip test gate entirely
  --batch-max-lines N      Max lines per review batch
  --output PATH            Output directory for reports (default: ./reports/)
  --scan                   Auto-scan mode: split repo into units and review each
  --plan-only              Scan and show plan only, don't run reviews
  --max-units N            Limit number of units to review (top N by priority)
  --resume SCAN_ID         Resume a previous scan from checkpoint
  --help                   Show help
```

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

## Output

Reports are saved to `./reports/` (or `--output`):

- **`<session_id>.json`** — full session state (all rounds, findings, fixes, verdict)
- **`<session_id>.md`** — human-readable report:
  - Per-round findings table (with confidence when multi-pass)
  - Low-confidence findings in a separate "Human Review" section
  - Fixes applied/rejected with explanations
  - Test results per round
  - Judge verdict with category scores and recommendations

In scan mode, additional aggregate reports:
- **`scan_<scan_id>.json`** — all unit sessions combined
- **`scan_<scan_id>.md`** — overview table, per-unit summaries, top findings, aggregate score

## Architecture

```
                         ┌────────────────────┐
                         │    Your Codebase    │
                         └─────────┬──────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                     Review Pipeline                          │
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
│   A) Single    — one flat pass                              │
│   B) Multi-Pass — N passes × different angles → vote        │
│   C) Layered   — architecture → interface → logic → security│
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
