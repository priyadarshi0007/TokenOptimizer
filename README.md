# smart-delegate

A modular, provider-agnostic token-cost optimizer for Claude Code. It
intercepts heavy file I/O and boilerplate code generation and routes them to
a cheap worker model (local Ollama or a cloud model like Gemini Flash)
instead of spending frontier-model tokens on grunt work.

## Quick start (drop this into an existing project)

These steps add smart-delegate to a project that already has its own repo —
scoped to that project only, nothing global.

**1. Have a worker model ready.** Check what you've already got before
pulling anything new:
```bash
which ollama && ollama list
```
Any local model works — you don't need the exact one in `config.yaml`
(step 4 covers swapping it in).

**2. Clone smart-delegate into the project, as a dotfolder:**
```bash
cd /path/to/your-project
git clone https://github.com/priyadarshi0007/TokenOptimizer.git .tokenoptimizer
```

**3. Install it into the project's virtualenv:**
```bash
source .venv/bin/activate
pip install -e .tokenoptimizer
```
This registers the `smart-delegate` CLI.

**4. Create a project-local config** so it doesn't affect other projects:
```bash
mkdir -p .smart-delegate
cp .tokenoptimizer/config.yaml .smart-delegate/config.yaml
```
Open `.smart-delegate/config.yaml` and point `model:` at whatever you
actually have pulled (from step 1):
```diff
- model: "gemma2:9b"
+ model: "gemma3:4b"
```
Project-local config always wins over `~/.smart-delegate/`, so this setup
stays scoped to this repo.

**5. Install the skill**, so Claude knows the delegation protocol:
```bash
mkdir -p .claude/skills
cp .tokenoptimizer/skills/smart-delegate.md .claude/skills/smart-delegate.md
```

**6. Wire up the enforcement hook.** Create (or edit) `.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/your-project/.tokenoptimizer/hooks/enforce-read-threshold.py"
          }
        ]
      }
    ]
  }
}
```
Use an absolute path to `enforce-read-threshold.py`. This is the layer that actually
blocks oversized raw reads — the skill alone is advisory.

**7. Verify the install:**
```bash
ollama serve &   # if it isn't already running
smart-delegate doctor
```
You should see the active provider, model, and guardrail settings printed
with no errors.

**8. Smoke-test a real delegation call:**
```bash
smart-delegate bulk-read .tokenoptimizer/smart_delegate/delegate.py \
  --instructions "In one sentence, what does this file do?"
```
A correct one-line summary with `cache_hit=False` confirms the round trip to
your worker model actually works.

**9. Housekeeping** — keep the tool's local cache out of your repo:
```bash
echo -e '\n# smart-delegate\n.smart_delegate_cache/' >> .gitignore
```

`.tokenoptimizer/`, `.smart-delegate/`, and `.claude/` are project-local by
design — decide for yourself whether to commit `.tokenoptimizer/` (vendored
copy) or `.gitignore` it and treat this repo as the source of truth instead.

## Components

```
smart-delegate/
├── README.md
├── pyproject.toml
├── config.yaml                  # default config (copy to ~/.smart-delegate/ or ./.smart-delegate/)
├── smart_delegate/
│   ├── __init__.py
│   ├── cli.py                   # `smart-delegate` CLI entrypoint
│   ├── config.py                # config loading/resolution
│   ├── delegate.py              # orchestrates guardrails -> cache -> provider
│   ├── cache.py                 # content-hashed local cache
│   ├── sanitize.py              # path exclusion + secret redaction
│   └── providers/
│       ├── base.py              # Provider ABC
│       ├── registry.py          # pluggable provider registry
│       ├── ollama.py            # local Ollama backend
│       └── gemini.py            # Google Gemini Flash backend
├── hooks/
│   └── enforce-read-threshold.py       # Claude Code PreToolUse hook
└── skills/
    └── smart-delegate.md        # Claude Code skill definition
```

## Install

```bash
cd smart-delegate
pip install -e .
# or, for Gemini support:
pip install -e ".[gemini]"
```

Copy the config to a discoverable location (project-local wins over
user-global):

```bash
mkdir -p ~/.smart-delegate
cp config.yaml ~/.smart-delegate/config.yaml
```

Edit `active_provider` and the relevant provider block. For fully local
operation (recommended default — no code leaves your machine):

```yaml
active_provider: ollama
providers:
  ollama:
    kind: ollama
    base_url: "http://localhost:11434"
    model: "gemma2:9b"
```

Make sure `ollama serve` is running and the model is pulled:
```bash
ollama pull gemma2:9b
```

For Gemini, set `active_provider: gemini` and export the API key:
```bash
export GOOGLE_API_KEY="..."
```

Verify the setup:
```bash
smart-delegate doctor
```

## CLI usage

```bash
# Delegate reading/summarizing a large file
smart-delegate bulk-read path/to/big_file.log --instructions "List all ERROR lines with timestamps"

# Delegate boilerplate code generation
smart-delegate code-write "Generate a Pydantic model for a User with id, email, created_at" \
  --context path/to/existing_model.py

# Delegate a new, self-contained file straight to disk — the generated code
# never enters the calling agent's context at all, only a short confirmation does
smart-delegate code-write "Generate a Pydantic model for a User with id, email, created_at" \
  --context path/to/existing_model.py --apply path/to/new_model.py

# Clear the local response cache
smart-delegate cache-clear

# Temporarily loosen the raw-read threshold for one session without editing config.yaml
SMART_DELEGATE_MIN_LINES=800 smart-delegate doctor
```

## Wiring up the Claude Code hook

Add to your `.claude/settings.json` (project) or `~/.claude/settings.json`
(global):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/smart-delegate/hooks/enforce-read-threshold.py"
          }
        ]
      }
    ]
  }
}
```

This blocks raw `Read` calls and `cat`/`head`/`tail`/`less`/`more` invocations
via `Bash` on any file exceeding `guardrails.max_raw_read_lines` (default 300
lines), except files matching `guardrails.excluded_path_patterns` (secrets,
`.env`, `*.pem`, etc.), which are always allowed through raw and never
delegated. On block, Claude is told to use `smart-delegate bulk-read` instead.

## Installing the skill

Copy `skills/smart-delegate.md` into your Claude Code skills directory (e.g.
`~/.claude/skills/smart-delegate.md` or your project's `.claude/skills/`) so
Claude knows the delegation protocol and its boundaries.

## Guardrails

See [Core Operational Guardrails](#core-operational-guardrails) below —
enforced in `sanitize.py` (path exclusion + secret redaction), `cache.py`
(model-id-scoped cache keys), and each provider module (hard request
timeouts, clean error surfacing).

### Core Operational Guardrails

**Never delegated, by design:**
- Surgical/precise code edits — worker output isn't line-number-reliable;
  read and edit exact sections yourself.
- Complex reasoning, security analysis, race conditions, crypto/thread-safety
  review — stays in the frontier model's own context.
- Secrets/compliance files (`.env`, `*.pem`, `*.key`, `id_rsa`, credential
  files) — refused by `sanitize.assert_path_allowed` in both the CLI and the
  hook, regardless of provider.

**Enforcement:**
- The `PreToolUse` hook enforces the read threshold programmatically —
  it does not rely on Claude following the skill's advice.
- The hook also matches `Bash` invocations of `cat`/`head`/`tail`/`less`/`more`,
  not just the native `Read` tool.
- Every provider wrapper enforces its own hard `timeout_seconds` (default 30s)
  and raises a clean `ProviderError`/`ProviderTimeoutError` rather than
  hanging the session.
- Inline secret patterns (API keys, AWS secrets, bearer tokens, private key
  blocks, passwords) are redacted from any payload before it is sent to a
  provider, via `sanitize.redact_secrets`, on top of the path-level exclusion.

**Data privacy:** switch `active_provider` to `ollama` in `config.yaml` to
keep all worker inference fully local. If using a cloud provider (e.g.
`gemini`), confirm your data privacy agreements cover secondary model
inference calls before delegating anything sensitive-but-not-secret.

## Design notes

A few implementation choices worth calling out:

- **XML-tag wrapping** (`<file_content>…</file_content>`, `<instructions>…</instructions>`)
  around content sent to the worker, rather than a plain text fence — cheap
  models hold this boundary more reliably than freeform delimiters.
- **Low worker temperature** (`temperature: 0.2` by default) — delegated
  tasks are read/write grunt work, not creative generation, and low
  temperature also makes near-duplicate inputs more likely to produce
  cache-identical output.
- **`SMART_DELEGATE_MIN_LINES` env override** for the read threshold, so it
  can be loosened for one session without editing `config.yaml`.
- **`code-write --apply`** — write the draft straight to disk instead of
  printing it, so the generated tokens never enter the calling agent's own
  context at all. This is where code-write's real savings are: not avoiding
  a *read*, but avoiding a *generation* the agent would otherwise have to
  produce and hold in its own context.
- Expect a real latency cost: each delegated call is a 10–30s round trip.
  Don't retry in a loop on failure (see Guardrails above) and expect large
  code-write tasks to need splitting if they'd exceed the worker's timeout.
