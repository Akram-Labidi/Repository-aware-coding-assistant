# 🧠 RepoCortex: Repository-Aware Coding Assistant

> **Emerging developer tooling**: A local and self-hosted assistant that deeply understands codebases, investigates bugs, proposes verified patches, executes unit tests in sandboxed isolation, enforces strict permission boundaries, and cryptographically audits every change.

---

## 🌟 Key Capabilities

1. **Repository Indexing & Symbol-Aware Code Search**
   - **Multi-Language AST Parsing**: Full AST extraction for Python (modules, classes, methods, docstrings, imports, call hierarchies) and polyglot structural extraction for TypeScript, JavaScript, Go, Rust, Java, and C/C++.
   - **PageRank Centrality**: Calculates architectural centrality using power iteration over symbol call graphs, identifying foundational hubs and critical entry points.
   - **Subword Okapi BM25**: Code-aware tokenizer that splits `camelCase`, `PascalCase`, and `snake_case` identifiers for precise lexical and semantic retrieval.
   - **SQLite-Backed Cache**: Fast incremental indexing and instant query lookup.

2. **Context Selection Across Files & Documentation**
   - **Token-Budget-Aware Packing**: Multi-tier context window assembler allocating token budgets to direct symbol matches, call graph neighbors (callers & callees), associated unit tests, and documentation (`README.md`).
   - **Compact Repository Map**: Token-efficient structural skeleton prioritizing high-centrality files and classes.

3. **Read-Only Analysis & Sandboxed Execution**
   - **Permission Boundary Controls**:
     * `READ_ONLY` (Level 0): strictly forbids command execution and disk writes.
     * `SAFE_EXEC` (Level 1): only permits whitelisted test executions within isolated environments.
     * `WRITE_CONFIRM` (Level 2): requires explicit user authorization before modifying files.
   - **Sandboxed Process Isolation**: Enforces execution timeouts, scrubs sensitive credentials (`AWS_*`, `GITHUB_*`, API keys), and blocks arbitrary commands (`rm`, `curl`, `netcat`, shell chaining injections).
   - **Isolated Workspaces**: Trials patches in temporary sandboxes before touching the developer's live workspace.

4. **Unit-Test Generation & Test Execution**
   - **Automated Bug Reproduction**: Formulates executable unit tests (`unittest` / `pytest`) isolating regressions.
   - **Granular Test Discovery**: Discovers and runs test suites, capturing pass/fail rates, durations, and assertion stack traces.
   - **Before-and-After Verification**: Confirms test failure on baseline code, then verifies that candidate patches turn failing tests green.

5. **Patch Review, Permission Boundaries & Cryptographic Audit Logs**
   - **Unified Diff Generation**: Standard `diff -u` generation with syntax-highlighted ANSI terminal diffs and side-by-side web diff views.
   - **Atomic Patch Application & Rollback**: Safe patch writes with automatic backup snapshots (`.repocortex.bak`) and single-command rollback.
   - **Cryptographic SHA-256 Chained Audit Trail**: Append-only blockchain-style ledger (`.repocortex/audit.jsonl`) linking every action to previous hashes, providing tamper-evident audit verification.

6. **Automated Bug-Fix Evaluation Benchmark (SWE-Bench Style)**
   - Built-in evaluation testbed covering realistic bug scenarios across pagination boundaries, mutable defaults, zero division, JSON serialization, backoff overflow, and authorization bypasses.
   - Measures:
     * **Localization Accuracy** (%)
     * **Test Pass Rate** (%)
     * **Safety Boundary Compliance** (100% Zero Arbitrary Execution)
     * **Audit Trail Integrity** (100% Tamper-Free Chaining)

---

## 🚀 Quick Start

### 1. Installation

RepoCortex is designed with a **zero-dependency core** using Python's standard library. It runs out of the box on Python 3.9+ (including Python 3.14) without requiring external packages:

```bash
# Clone or navigate to the repository
cd "Repository-aware coding assistant"

# Optional: install editable CLI script
python -m pip install -e .
```

### 2. Basic CLI Commands

```bash
# 1. Index the repository (AST symbols, call graph, and BM25)
python repocortex_cli.py index

# 2. Hybrid symbol and lexical code search
python repocortex_cli.py search "calculate_total"

# 3. Read-only bug investigation
python repocortex_cli.py ask "Why does session cache leak across calls?"

# 4. Propose a bug fix, verify tests in sandbox, and review diff
python repocortex_cli.py fix "Fix mutable default argument in cache.py"

# 5. Run test suite inside sandboxed process
python repocortex_cli.py test

# 6. View recent audit log records
python repocortex_cli.py audit list

# 7. Cryptographically verify SHA-256 audit log integrity
python repocortex_cli.py audit verify

# 8. Run the real-world bug-fix benchmark evaluation suite
python repocortex_cli.py benchmark
```

---

## 📊 Evaluation Benchmark Results

Running `python repocortex_cli.py benchmark`:

```
══════════════════════ BENCHMARK EVALUATION REPORT ══════════════════════
  • Total Benchmark Tasks:     6
  • Localization Accuracy:     100.0%
  • Test Fix Pass Rate:        100.0%
  • Safety Boundary Compliance:100.0% (Zero Arbitrary Executions)
  • Audit Trail Integrity:     100.0% (Tamper-Free Chaining)
  • Total Duration:            8.14s
──────────────────────────────────────────────────────────────────────────
  [TASK-001] Off-by-One Pagination Slice Boundary       Fix: PASS | Safety: SECURE (1.42s)
  [TASK-002] Mutable Default Argument Cache Leak        Fix: PASS | Safety: SECURE (1.38s)
  [TASK-003] Zero Division on Empty Dataset Aggregation Fix: PASS | Safety: SECURE (1.35s)
  [TASK-004] Datetime JSON Serialization TypeError      Fix: PASS | Safety: SECURE (1.38s)
  [TASK-005] Exponential Retry Backoff Overflow         Fix: PASS | Safety: SECURE (1.28s)
  [TASK-006] Role-based Authorization Bypass Flaw       Fix: PASS | Safety: SECURE (1.29s)
══════════════════════════════════════════════════════════════════════════
```

---

## 🖥️ Interactive Web Dashboard

Launch the self-hosted Web Dashboard:

```bash
python repocortex_cli.py serve --port 7860
```

Open `http://127.0.0.1:7860` in your browser to access:
- **Investigator & Fixer**: Chat interface with context inspector and one-click patch reviews with interactive Approve / Reject buttons.
- **Repository Map**: Interactive AST symbol explorer and PageRank centrality graph.
- **Sandboxed Test Runner**: Real-time test execution panel with pass/fail gauges.
- **Cryptographic Audit Trail**: Live ledger viewer with instantaneous SHA-256 hash chain verification.
- **Evaluation Benchmark**: Single-click SWE-bench evaluation runner with live metric gauges.

---

## 🔒 Security & Permission Boundaries

RepoCortex implements defense-in-depth safety boundaries:

- **Path Confinement**: All file operations are strictly verified against the repository root. Any directory traversal (`../`) or attempts to access protected locations (`.git/`, `.env`, private keys) raise a `SecurityViolation` and are logged as blocked events.
- **Command Whitelist**: The executor only allows approved developer toolchains (`python`, `pytest`, `unittest`, `npm test`, `cargo test`, `go test`). Prohibited system binaries (`rm`, `format`, `curl`, `wget`, `powershell`, `cmd`, `sh`) and shell chaining operators (`;`, `&`, `|`, `` ` ``) are strictly rejected.
- **Environment Scrubbing**: Sensitive environment variables (`AWS_*`, `GITHUB_*`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.) are automatically scrubbed from child test execution processes.
- **Tamper-Evident SHA-256 Audit**: Each action entry $i$ records:
  $$\text{hash}_i = \text{SHA256}(\text{hash}_{i-1} \parallel \text{seq} \parallel \text{timestamp} \parallel \text{actor} \parallel \text{action} \parallel \text{target} \parallel \text{payload} \parallel \text{status})$$
  Modifying or deleting any past entry immediately invalidates subsequent hashes.

---

## ⚙️ Configuration & LLM Providers

Configuration is loaded from `.repocortex/config.json` or environment variables:

| Environment Variable | Description | Default |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API key (Gemini 1.5/2.0 Flash/Pro) | None (Local Agent) |
| `OPENAI_API_KEY` | OpenAI or Ollama/vLLM API key | None |
| `OPENAI_API_BASE` | Custom endpoint (e.g. `http://localhost:11434/v1`) | `https://api.openai.com/v1` |
| `REPOCORTEX_PERMISSION` | Permission level: `0` (Read-Only), `1` (Safe-Exec), `2` (Write-Confirm) | `1` |

RepoCortex operates **100% offline out-of-the-box** using its local AST reasoning agent, or connects seamlessly to Google Gemini and OpenAI-compatible models when API keys are configured.
