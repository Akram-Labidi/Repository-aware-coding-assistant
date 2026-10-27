"""Zero-dependency HTTP Server & REST API for RepoCortex Web Dashboard.

Provides interactive endpoints for indexing, symbol browsing, bug investigation,
patch review, test execution, audit verification, and benchmark evaluation.
"""

from __future__ import annotations
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from repocortex.assistant.engine import RepoCortexAssistant
from repocortex.benchmark.runner import BenchmarkRunner
from repocortex.core.types import FilePatch


class RepoCortexAPIHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler serving REST API and Web Dashboard."""

    assistant: RepoCortexAssistant
    static_dir: Path

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        body_bytes = self.rfile.read(content_len)
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if path == "/api/status":
            cfg = self.assistant.config
            self._send_json({
                "repo_root": str(cfg.abs_repo_root),
                "permission_level": cfg.permission_level.name,
                "permission_value": int(cfg.permission_level),
                "indexed_files": len(self.assistant.index.files),
                "indexed_symbols": len(self.assistant.index.symbols),
                "llm_provider": cfg.llm_provider,
            })
            return

        if path == "/api/files":
            file_list = []
            for fpath, node in self.assistant.index.files.items():
                file_list.append({
                    "path": fpath,
                    "language": node.language,
                    "lines": node.line_count,
                    "is_test": node.is_test_file,
                    "is_doc": node.is_doc_file,
                })
            self._send_json({"files": file_list})
            return

        if path == "/api/file":
            rel_path = query_params.get("path", [""])[0]
            content = self.assistant.index.get_file_content(rel_path)
            if content is not None:
                self._send_json({"path": rel_path, "content": content})
            else:
                self._send_json({"error": "File not found or outside repo boundary"}, status=404)
            return

        if path == "/api/symbols":
            sym_list = []
            for key, sym in self.assistant.index.symbols.items():
                pr = self.assistant.index.symbol_graph.get_centrality(sym.file_path, sym.name)
                sym_list.append({
                    "key": key,
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "kind": sym.kind.value if hasattr(sym.kind, "value") else str(sym.kind),
                    "file_path": sym.file_path,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "signature": sym.signature,
                    "centrality": round(pr, 3),
                    "callers": sym.callers,
                    "callees": sym.callees,
                })
            self._send_json({"symbols": sym_list})
            return

        if path == "/api/audit":
            limit = int(query_params.get("limit", [50])[0])
            entries = self.assistant.audit_logger.read_entries(limit=limit)
            self._send_json({"entries": [e.to_dict() for e in entries]})
            return

        if path == "/api/audit/verify":
            is_valid, msg, count = self.assistant.audit_logger.verify_integrity()
            self._send_json({"valid": is_valid, "message": msg, "count": count})
            return

        if path == "/api/repo-map":
            repomap = self.assistant.context_selector.repo_map_gen.generate_map(max_tokens=2000)
            self._send_json({"repo_map": repomap})
            return

        # Serve static assets
        if path == "/" or path == "/index.html":
            self._serve_static_file("index.html", "text/html")
        elif path == "/styles.css":
            self._serve_static_file("styles.css", "text/css")
        elif path == "/app.js":
            self._serve_static_file("app.js", "application/javascript")
        else:
            self._send_json({"error": "Not Found"}, status=404)

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        body = self._read_json_body()

        if path == "/api/index":
            force = body.get("force", False)
            stats = self.assistant.index_repo(force=force)
            self._send_json({"success": True, "stats": stats})
            return

        if path == "/api/search":
            query = body.get("query", "")
            limit = body.get("limit", 15)
            results = self.assistant.search_code(query, limit=limit)
            self._send_json({"results": [r.to_dict() for r in results]})
            return

        if path == "/api/investigate":
            query = body.get("query", "")
            target_files = body.get("target_files", None)
            res = self.assistant.investigate_bug(query, target_files=target_files)
            self._send_json(res)
            return

        if path == "/api/fix":
            query = body.get("query", "")
            target_files = body.get("target_files", None)
            verify = body.get("verify_in_sandbox", True)
            res = self.assistant.propose_fix(query, target_files=target_files, verify_in_sandbox=verify)
            self._send_json(res)
            return

        if path == "/api/apply-patch":
            patch_data = body.get("patch", {})
            user_confirmed = body.get("user_confirmed", True)

            patch = FilePatch(
                file_path=patch_data.get("file_path", ""),
                action=patch_data.get("action", "modify"),
                diff=patch_data.get("diff", ""),
                proposed_content=patch_data.get("proposed_content", None),
            )
            success, msg = self.assistant.apply_patch(patch, user_confirmed=user_confirmed)
            self._send_json({"success": success, "message": msg})
            return

        if path == "/api/test":
            target = body.get("target", None)
            run = self.assistant.test_runner.run_tests(test_target=target)
            self._send_json({"test_run": run.to_dict()})
            return

        if path == "/api/benchmark/run":
            runner = BenchmarkRunner()
            summary = runner.run_benchmark()
            self._send_json(summary)
            return

        self._send_json({"error": "Endpoint not found"}, status=404)

    def _serve_static_file(self, rel_filename: str, content_type: str) -> None:
        file_path = self.static_dir / rel_filename
        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            return

        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(500)
            self.end_headers()


def run_server(assistant: RepoCortexAssistant, host: str = "127.0.0.1", port: int = 7860) -> None:
    static_dir = Path(__file__).parent / "static"
    RepoCortexAPIHandler.assistant = assistant
    RepoCortexAPIHandler.static_dir = static_dir

    server_address = (host, port)
    httpd = HTTPServer(server_address, RepoCortexAPIHandler)
    url = f"http://{host}:{port}"

    print(f"\n\033[92m\033[1m[RepoCortex] Web Dashboard is live at: {url}\033[0m")
    print(f"\033[96m* Repository Root: {assistant.config.abs_repo_root}\033[0m")
    print(f"\033[96m* Permission Boundary: {assistant.config.permission_level.name}\033[0m")
    print(f"\033[90mPress Ctrl+C to stop server.\033[0m\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()
