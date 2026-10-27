"""Configuration management for RepoCortex."""

from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from repocortex.core.types import PermissionLevel


@dataclass
class RepoCortexConfig:
    repo_root: str = "."
    storage_dir: str = ".repocortex"
    permission_level: PermissionLevel = PermissionLevel.SAFE_EXEC
    max_context_tokens: int = 8192
    command_timeout_sec: float = 20.0
    llm_provider: str = "local"  # "local", "gemini", "openai", "anthropic"
    llm_model: str = "gemini-1.5-pro"
    api_key: Optional[str] = None
    web_host: str = "127.0.0.1"
    web_port: int = 7860
    
    # Security Whitelist & Blacklist
    allowed_commands: List[str] = field(default_factory=lambda: [
        "python", "python3", "pytest", "unittest", "node", "npm test",
        "cargo test", "go test"
    ])
    prohibited_commands: List[str] = field(default_factory=lambda: [
        "rm", "del", "format", "curl", "wget", "powershell", "cmd.exe",
        "bash", "sh", "mkfs", "dd", "netcat", "nc", "ssh", "scp", "shutdown"
    ])
    protected_paths: List[str] = field(default_factory=lambda: [
        ".git", ".env", ".secrets", "id_rsa", "id_ed25519", "*.pem", "*.key"
    ])

    @property
    def abs_repo_root(self) -> Path:
        return Path(self.repo_root).resolve()

    @property
    def abs_storage_dir(self) -> Path:
        p = Path(self.storage_dir)
        if not p.is_absolute():
            p = self.abs_repo_root / p
        return p.resolve()

    @property
    def db_path(self) -> Path:
        return self.abs_storage_dir / "repocortex.db"

    @property
    def audit_log_path(self) -> Path:
        return self.abs_storage_dir / "audit.jsonl"

    def ensure_storage_dir(self) -> Path:
        d = self.abs_storage_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def load(cls, repo_path: str = ".") -> RepoCortexConfig:
        root = Path(repo_path).resolve()
        config_file = root / ".repocortex" / "config.json"
        
        cfg = cls(repo_root=str(root))
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "permission_level" in data:
                    data["permission_level"] = PermissionLevel(data["permission_level"])
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:
                pass
        
        # Override with environment variables if present
        if "REPOCORTEX_PERMISSION" in os.environ:
            try:
                cfg.permission_level = PermissionLevel(int(os.environ["REPOCORTEX_PERMISSION"]))
            except ValueError:
                pass
        if "GEMINI_API_KEY" in os.environ:
            cfg.api_key = os.environ["GEMINI_API_KEY"]
            if cfg.llm_provider == "local":
                cfg.llm_provider = "gemini"
        elif "OPENAI_API_KEY" in os.environ:
            cfg.api_key = os.environ["OPENAI_API_KEY"]
            if cfg.llm_provider == "local":
                cfg.llm_provider = "openai"

        return cfg

    def save(self) -> None:
        self.ensure_storage_dir()
        config_file = self.abs_storage_dir / "config.json"
        data = {
            "repo_root": str(self.abs_repo_root),
            "storage_dir": self.storage_dir,
            "permission_level": int(self.permission_level),
            "max_context_tokens": self.max_context_tokens,
            "command_timeout_sec": self.command_timeout_sec,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "allowed_commands": self.allowed_commands,
            "prohibited_commands": self.prohibited_commands,
            "protected_paths": self.protected_paths,
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
