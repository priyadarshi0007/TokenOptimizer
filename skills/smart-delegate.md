---
name: smart-delegate
description: Route heavy file reads and boilerplate code generation to a cheap local/cloud worker model instead of spending frontier context on grunt work. Use when a file exceeds the configured line threshold, or when asked to generate boilerplate/pattern-matching code (CRUD scaffolds, DTOs, repetitive tests, config translation) rather than surgical edits.
---

# smart-delegate

`smart-delegate` offloads two kinds of grunt work to a cheaper worker model
(local Ollama or a cloud model like Gemini Flash, per `config.yaml`):

1. **Bulk reading / summarizing large files** — instead of reading a 3,000-line
   log or generated file into your own context, delegate it and get back a
   focused summary.
2. **Boilerplate code generation** — instead of hand-writing repetitive
   scaffolding (CRUD handlers, DTOs, test fixtures, config translation), have
   the worker draft it, then you review and integrate.

A native `PreToolUse` hook (`enforce-read-threshold.py`) already **enforces** the
read-size threshold — it will block a raw `Read`/`cat`/`head`/`tail` call on
an oversized file and tell you to use `smart-delegate bulk-read` instead. This
skill explains the protocol so you use the tool well, not just when forced to.

## When to delegate

- Reading a file above the configured threshold (`guardrails.max_raw_read_lines`,
  default 300 lines) purely to extract information, find something, or
  summarize it.
- Generating new, self-contained boilerplate: a CRUD scaffold, a DTO/schema
  class, a batch of similar test cases, a config format translation.

## When NEVER to delegate (hard boundaries)

- **Surgical edits to existing code.** Worker models do not reliably preserve
  exact line numbers or byte-for-byte context. If you need to modify specific
  lines, read that exact section yourself (e.g. with an offset/limit range)
  and edit it directly with your own tools.
- **Complex reasoning or security-sensitive analysis.** Architecture
  decisions, subtle bug hunts, race conditions, cryptographic or
  thread-safety review must stay in your own context. Never ask a worker
  model to find or reason about these — it lacks the judgment and the
  worker's output cannot be trusted for correctness-critical reasoning.
- **Secrets and compliance-sensitive files.** `.env`, `*.pem`, `*.key`,
  `id_rsa`, credentials files, anything matching
  `guardrails.excluded_path_patterns` in `config.yaml`. The CLI and hook both
  refuse these automatically — read them directly yourself instead.

## How to use it

### Bulk read
```
smart-delegate bulk-read path/to/large_file.log --instructions "List all ERROR-level lines with their timestamps"
```
The worker model receives the file content (secrets redacted) and your
instructions, and returns a focused answer — not the raw file.

### Code write
```
smart-delegate code-write "Generate a Pydantic model for a User with id, email, created_at" --context path/to/existing_model.py
```
`--context` is optional and provides an existing file as a style/pattern
reference. The output is a **draft to review**, not a diff — treat it as a
starting point, read it fully, and integrate it yourself with your own edit
tools. Never blindly apply worker output to existing files.

**For a genuinely new, self-contained file** (a fresh scaffold, not something
being merged into existing code), prefer `--apply`:
```
smart-delegate code-write "Generate a Pydantic model for a User with id, email, created_at" \
  --context path/to/existing_model.py --apply path/to/new_model.py
```
This writes the draft straight to disk and prints only a short confirmation —
the generated code never enters your own context at all, which is where the
real token savings are for code-write (not just avoiding *reading* a file,
but avoiding *generating* one). Still open and read the file afterward before
trusting it; `--apply` skips your context, not your review.

### Cache
Identical `(task, model, content)` calls are served from a local
content-hash cache (`.smart_delegate_cache/` by default) so repeated
delegation of the same file/prompt costs nothing after the first call. Run
`smart-delegate cache-clear` if you need to force a refresh.

### Doctor
Run `smart-delegate doctor` if a delegation call fails, to check config
resolution and provider connectivity before retrying.

## Failure handling

If `smart-delegate` reports a `PROVIDER ERROR` (timeout, unreachable
Ollama/API), do not retry in a loop. Fall back to reading the file yourself
in bounded chunks (using offset/limit) rather than stalling on the worker.

## Data privacy

The active provider is configured in `config.yaml` (`active_provider`). If it
points at a cloud provider (e.g. `gemini`), file content leaves the machine
for that call. If you are working in a context with strict data-boundary
requirements, confirm the active provider is `ollama` (fully local) before
delegating anything sensitive-but-not-secret (e.g. proprietary business
logic you'd still rather not send externally).
