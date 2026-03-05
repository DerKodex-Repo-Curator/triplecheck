# Code Review Loop

Multi-agent, model-agnostic automated code review pipeline. Three roles (reviewer, coder, judge) iterate on your codebase until convergence — any role can be mapped to any LLM.

```
              ┌──────────────┐
              │  config.yml  │  role↔model mapping
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │ Orchestrator │  convergence, state, CI
              └──────┬───────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
  ┌────▼────┐  ┌─────▼─────┐  ┌───▼────┐
  │Reviewer │  │   Coder   │  │ Judge  │
  └────┬────┘  └─────┬─────┘  └───┬────┘
       │             │             │
   any model     any model     any model
```

## Install

```bash
cd /path/to/code-review-loop
pip install -e .
```

Requires Python 3.11+. Dependencies: `pyyaml`, `httpx`, `click`.

## Quick Start

```bash
# Review a project with default config
code-review --target ~/work/my-project

# Review specific files
code-review --target ~/work/my-project --include "*.py" --exclude "tests/*"

# Skip CI checks
code-review --target ~/work/my-project --skip-ci
```

## Configuration

All configuration lives in `config.yml`. There are four sections:

### 1. Roles

Define the three pipeline roles and their system prompts:

```yaml
roles:
  reviewer:
    description: "Senior code reviewer"
    prompt_file: prompts/reviewer.txt
  coder:
    description: "Expert developer"
    prompt_file: prompts/coder.txt
  judge:
    description: "Final arbiter"
    prompt_file: prompts/judge.txt
```

Custom prompts: edit the files in `prompts/` or point `prompt_file` to your own.

### 2. Models

Define available LLMs. Three provider types are supported:

```yaml
models:
  # claude -p CLI
  claude-opus:
    provider: claude-cli
    model: opus                    # opus | sonnet | haiku

  # codex CLI
  codex:
    provider: codex-cli

  # Any OpenAI-compatible API (vLLM, Qwen, DeepSeek, OpenRouter, etc.)
  qwen-local:
    provider: openai-compat
    base_url: http://localhost:8000
    model: qwen3.5
    max_tokens: 8192
    temperature: 0.1

  # Remote API with auth
  deepseek:
    provider: openai-compat
    base_url: https://api.deepseek.com
    model: deepseek-coder
    api_key_env: DEEPSEEK_API_KEY  # reads from this env var
```

### 3. Assignments

Map roles to models. This is the only section you need to change to swap models:

```yaml
assignments:
  reviewer: codex          # codex reviews the code
  coder: qwen-local        # local model applies fixes
  judge: claude-opus       # claude makes final judgment
```

### 4. Pipeline Settings

```yaml
pipeline:
  max_rounds: 4              # max review-fix iterations
  batch_max_lines: 6000      # split large projects into batches of this size
  severity_threshold: warning # only fix findings at this level or above
                              # options: error | warning | suggestion
  auto_style_fix: true        # run ruff/black after each coder round
```

## CLI Reference

```
code-review [OPTIONS]

Options:
  --target PATH            Project directory to review (required)
  --config PATH            Config file path (default: ./config.yml)
  --reviewer MODEL_NAME    Override reviewer model from config
  --coder MODEL_NAME       Override coder model from config
  --judge MODEL_NAME       Override judge model from config
  --max-rounds N           Override max rounds
  --include PATTERN        File glob filter (repeatable)
  --exclude PATTERN        Exclude pattern (repeatable)
  --ci-cmd COMMAND         Custom CI command (auto-detected by default)
  --skip-ci                Skip CI gate entirely
  --output PATH            Output directory for reports (default: ./reports/)
  --help                   Show help
```

### Override models per-run

No need to edit config.yml — override on the command line:

```bash
code-review --target . --reviewer claude-sonnet --coder deepseek --judge claude-opus
```

### Examples

```bash
# All-local review (requires OpenAI-compat server on localhost:8000)
code-review --target ~/work/my-project \
  --reviewer qwen-local --coder qwen-local --judge qwen-local \
  --skip-ci

# Strict mode — only fix errors, 2 rounds max
code-review --target . --max-rounds 2

# Custom CI command
code-review --target . --ci-cmd "python3.12 -m pytest tests/ -x"

# Review a single file
code-review --target ~/work/my-project --include "src/auth.py"
```

## Pipeline Flow

Each round:

1. **Reviewer** analyzes files in batches, returns JSON findings with severity
2. **Coder** fixes each file or rejects findings with reasoning
3. **Auto-style** runs `ruff --fix` / `black` if available
4. **CI gate** runs auto-detected tests (pytest, npm test, cargo test, etc.)

The loop stops when any convergence condition is met:
- Zero findings at or above the severity threshold
- Max rounds reached
- Coder rejected all findings (no progress possible)
- CI regression (tests broke after a fix)
- Oscillation (same finding reappears after 2 rounds)

After convergence, the **Judge** evaluates all rounds and produces a verdict with scores.

## Output

Reports are saved to `./reports/` (or `--output`):

- `<session_id>.json` — full session state (all rounds, findings, fixes)
- `<session_id>.md` — markdown report with scores, findings table, verdict

## Adding a New Provider

1. Create `code_review/providers/my_provider.py`
2. Subclass `BaseProvider` and implement `review()`, `fix()`, `judge()`
3. Register in `code_review/roles.py` → `PROVIDER_MAP`
4. Add model entries in `config.yml` with `provider: my-provider`
# code-review-loop
