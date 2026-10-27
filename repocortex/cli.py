"""RepoCortex Command-Line Interface.

Rich terminal interface for repository indexing, symbol search, bug fixing,
sandboxed testing, cryptographic audit log verification, and benchmark evaluation.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

# Ensure utf-8 encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from repocortex.assistant.engine import RepoCortexAssistant
from repocortex.benchmark.runner import BenchmarkRunner
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import PermissionLevel
from repocortex.sandbox.patch_manager import PatchManager


# Terminal ANSI Colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
GRAY = "\033[90m"


def print_banner():
    banner = f"""
{CYAN}{BOLD}╔═══════════════════════════════════════════════════════════════╗
║   RepoCortex: Repository-Aware Coding Assistant v1.0.0       ║
║   AST Symbols • BM25 • Sandboxed Execution • Cryptographic    ║
╚═══════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def cmd_index(assistant: RepoCortexAssistant, args: argparse.Namespace):
    print(f"{BLUE}Indexing repository at: {assistant.config.abs_repo_root}...{RESET}")
    stats = assistant.index_repo(force=args.force)
    print(f"{GREEN}✓ Indexing completed in {stats['duration_sec']}s{RESET}")
    print(f"  • Files indexed:   {stats['files_indexed']}")
    print(f"  • Symbols indexed: {stats['symbols_indexed']}")


def cmd_search(assistant: RepoCortexAssistant, args: argparse.Namespace):
    query = " ".join(args.query)
    print(f"{BLUE}Searching for '{query}'...{RESET}\n")
    results = assistant.search_code(query, limit=args.limit)

    if not results:
        print(f"{YELLOW}No symbols or code snippets matched '{query}'. Try running 'repocortex index'.{RESET}")
        return

    for i, res in enumerate(results, 1):
        match_tag = f"[{res.match_type.upper()}]"
        sym_info = f" • {res.symbol.kind.value} {res.symbol.qualified_name}" if res.symbol else ""
        print(f"{CYAN}{i}. {res.file_path}:{res.start_line}{sym_info} {GRAY}{match_tag} (score: {res.score:.2f}){RESET}")
        if res.snippet:
            snip_lines = res.snippet.strip().splitlines()[:4]
            for sl in snip_lines:
                print(f"   {GRAY}|{RESET} {sl}")
        print()


def cmd_investigate(assistant: RepoCortexAssistant, args: argparse.Namespace):
    query = " ".join(args.query)
    print(f"{BLUE}Investigating: {query}...{RESET}\n")
    report = assistant.investigate_bug(query)
    print(report["analysis"])


def cmd_fix(assistant: RepoCortexAssistant, args: argparse.Namespace):
    query = " ".join(args.query)
    print(f"{BLUE}Analyzing and synthesizing fix for: {query}...{RESET}\n")

    res = assistant.propose_fix(query, verify_in_sandbox=not args.no_sandbox)

    if not res.get("success"):
        print(f"{RED}✗ {res.get('message', 'Failed to generate patch.')}{RESET}")
        return

    patches = res.get("raw_patches", [])
    if not patches:
        print(f"{YELLOW}No modifications were suggested.{RESET}")
        return

    print(f"{GREEN}✓ Proposed {len(patches)} patch(es):{RESET}\n")

    for p in patches:
        print(f"{BOLD}File: {p.file_path} ({p.action}){RESET}")
        print(PatchManager.format_ansi_diff(p.diff))
        print()

    if res.get("tests_verified"):
        print(f"{GREEN}✓ Tests PASSED in sandboxed trial environment!{RESET}\n")
    else:
        print(f"{YELLOW}⚠ Tests either did not pass or no baseline tests were found.{RESET}\n")

    # Interactive Permission Boundary Confirmation
    if assistant.config.permission_level == PermissionLevel.READ_ONLY:
        print(f"{YELLOW}[READ_ONLY MODE] File modifications are locked. Patches were NOT applied.{RESET}")
        return

    if not args.yes:
        confirm = input(f"{BOLD}Apply these changes to repository? [y/N]: {RESET}").strip().lower()
        if confirm != "y":
            print(f"{YELLOW}Patch rejected by developer. No files were modified.{RESET}")
            assistant.audit_logger.log("REJECT_PATCH", query[:80], actor="user", status="rejected")
            return

    for p in patches:
        success, msg = assistant.apply_patch(p, user_confirmed=True)
        if success:
            print(f"{GREEN}✓ {msg}{RESET}")
        else:
            print(f"{RED}✗ {msg}{RESET}")


def cmd_test(assistant: RepoCortexAssistant, args: argparse.Namespace):
    target = args.target
    print(f"{BLUE}Running test suite in sandboxed environment...{RESET}")
    run = assistant.test_runner.run_tests(test_target=target)

    if run.all_passed:
        print(f"{GREEN}✓ ALL TESTS PASSED: {run.passed}/{run.total} tests in {run.duration_sec:.2f}s{RESET}")
    else:
        print(f"{RED}✗ TESTS FAILED: {run.failed} failed, {run.errors} errors (out of {run.total}) in {run.duration_sec:.2f}s{RESET}")
        print(f"\n{run.raw_output}")


def cmd_audit(assistant: RepoCortexAssistant, args: argparse.Namespace):
    sub = args.audit_cmd
    if sub == "verify":
        print(f"{BLUE}Verifying cryptographic SHA-256 chain integrity...{RESET}")
        is_valid, msg, count = assistant.audit_logger.verify_integrity()
        if is_valid:
            print(f"{GREEN}✓ AUDIT INTEGRITY VERIFIED: {msg}{RESET}")
        else:
            print(f"{RED}✗ TAMPER DETECTED: {msg}{RESET}")
            sys.exit(1)
    else:
        entries = assistant.audit_logger.read_entries(limit=args.limit)
        print(f"{BOLD}Recent Audit Log Records ({len(entries)} entries):{RESET}\n")
        for e in entries:
            stat_color = GREEN if e.status == "success" else (RED if e.status in ("failed", "blocked") else YELLOW)
            print(f"[{e.seq}] {e.timestamp} | {e.actor.upper()} | {BOLD}{e.action}{RESET} -> {e.target} | {stat_color}{e.status}{RESET}")
            print(f"     Hash: {GRAY}{e.current_hash[:16]}...{RESET}")


def cmd_benchmark(assistant: RepoCortexAssistant, args: argparse.Namespace):
    print(f"{BLUE}{BOLD}Running Automated Bug-Fix Evaluation Benchmark...{RESET}\n")
    runner = BenchmarkRunner()
    summary = runner.run_benchmark()

    print(f"\n{BOLD}══════════════════════ BENCHMARK EVALUATION REPORT ══════════════════════{RESET}")
    print(f"  • Total Benchmark Tasks:     {summary['total_tasks']}")
    print(f"  • Localization Accuracy:     {GREEN if summary['localization_accuracy_pct'] > 80 else YELLOW}{summary['localization_accuracy_pct']}%{RESET}")
    print(f"  • Test Fix Pass Rate:        {GREEN if summary['test_pass_rate_pct'] > 80 else YELLOW}{summary['test_pass_rate_pct']}%{RESET}")
    print(f"  • Safety Boundary Compliance:{GREEN}{summary['safety_compliance_pct']}% (Zero Arbitrary Executions){RESET}")
    print(f"  • Audit Trail Integrity:     {GREEN}{summary['audit_integrity_pct']}% (Tamper-Free Chaining){RESET}")
    print(f"  • Total Duration:            {summary['total_duration_sec']}s")
    print(f"{BOLD}──────────────────────────────────────────────────────────────────────────{RESET}")

    for t in summary["task_results"]:
        status_icon = f"{GREEN}PASS{RESET}" if t["tests_passed_after_patch"] else f"{RED}FAIL{RESET}"
        safety_icon = f"{GREEN}SECURE{RESET}" if t["safety_passed"] else f"{RED}BREACH{RESET}"
        print(f"  [{t['task_id']}] {t['task_name']:<42} Fix: {status_icon} | Safety: {safety_icon} ({t['execution_time_sec']}s)")

    print(f"{BOLD}══════════════════════════════════════════════════════════════════════════{RESET}\n")


def cmd_serve(assistant: RepoCortexAssistant, args: argparse.Namespace):
    from repocortex.web.server import run_server
    host = args.host or assistant.config.web_host
    port = args.port or assistant.config.web_port
    run_server(assistant, host=host, port=port)


def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--repo", default=".", help="Target repository directory (default: current working dir)")
    common_parser.add_argument("--readonly", action="store_true", help="Force READ_ONLY analysis mode")

    parser = argparse.ArgumentParser(
        prog="repocortex",
        description="RepoCortex: Repository-aware coding assistant with AST search, sandboxing, and audit logs.",
        parents=[common_parser],
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # index
    p_index = subparsers.add_parser("index", parents=[common_parser], help="Index repository AST, symbols, and BM25 search")
    p_index.add_argument("--force", action="store_true", help="Force rebuild index")

    # search
    p_search = subparsers.add_parser("search", parents=[common_parser], help="Search symbols and code in repository")
    p_search.add_argument("query", nargs="+", help="Search query")
    p_search.add_argument("--limit", type=int, default=8, help="Max results")

    # ask / investigate
    p_inv = subparsers.add_parser("ask", parents=[common_parser], help="Investigate code or ask questions about repository")
    p_inv.add_argument("query", nargs="+", help="Question or bug report")

    # fix
    p_fix = subparsers.add_parser("fix", parents=[common_parser], help="Synthesize bug fix, verify in sandbox, and review patch")
    p_fix.add_argument("query", nargs="+", help="Bug description or repair instruction")
    p_fix.add_argument("-y", "--yes", action="store_true", help="Apply patch without prompting")
    p_fix.add_argument("--no-sandbox", action="store_true", help="Skip sandboxed test verification")

    # test
    p_test = subparsers.add_parser("test", parents=[common_parser], help="Run test suite in sandboxed environment")
    p_test.add_argument("target", nargs="?", default=None, help="Optional test file or method")

    # audit
    p_audit = subparsers.add_parser("audit", parents=[common_parser], help="Inspect and verify cryptographic audit trail")
    p_audit.add_argument("audit_cmd", choices=["list", "verify"], default="list", nargs="?", help="Action: list or verify")
    p_audit.add_argument("--limit", type=int, default=20, help="Number of recent records to display")

    # benchmark
    p_bench = subparsers.add_parser("benchmark", parents=[common_parser], help="Run real-world bug-fix benchmark evaluation suite")

    # serve
    p_serve = subparsers.add_parser("serve", parents=[common_parser], help="Launch interactive Web Dashboard & REST API")
    p_serve.add_argument("--host", default="127.0.0.1", help="Web server host")
    p_serve.add_argument("--port", type=int, default=7860, help="Web server port")

    args = parser.parse_args()

    if not args.command:
        print_banner()
        parser.print_help()
        return

    cfg = RepoCortexConfig.load(args.repo)
    if args.readonly:
        cfg.permission_level = PermissionLevel.READ_ONLY

    assistant = RepoCortexAssistant(cfg)

    commands = {
        "index": cmd_index,
        "search": cmd_search,
        "ask": cmd_investigate,
        "fix": cmd_fix,
        "test": cmd_test,
        "audit": cmd_audit,
        "benchmark": cmd_benchmark,
        "serve": cmd_serve,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(assistant, args)


if __name__ == "__main__":
    main()
