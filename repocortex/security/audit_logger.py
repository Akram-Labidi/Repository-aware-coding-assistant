"""Cryptographic chained append-only audit logger.

Records every prompt, search, patch proposal, user approval, test execution,
and permission check. Uses SHA-256 blockchain-style chaining to ensure
tamper-evident audit integrity.
"""

from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import AuditEntry


class AuditLogger:
    """Tamper-evident cryptographically chained audit logger."""

    GENESIS_HASH = "0" * 64

    def __init__(self, config: RepoCortexConfig):
        self.config = config
        self.log_file = config.audit_log_path
        self._last_hash = self.GENESIS_HASH
        self._seq = 0
        self._init_log()

    def _init_log(self) -> None:
        self.config.ensure_storage_dir()
        if self.log_file.exists():
            # Read last line to initialize seq and last_hash
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    if lines:
                        last_entry = json.loads(lines[-1])
                        self._seq = last_entry["seq"] + 1
                        self._last_hash = last_entry["current_hash"]
            except Exception:
                pass

    def _compute_hash(
        self,
        prev_hash: str,
        seq: int,
        timestamp: str,
        actor: str,
        action: str,
        target: str,
        payload_json: str,
        status: str,
    ) -> str:
        data = f"{prev_hash}|{seq}|{timestamp}|{actor}|{action}|{target}|{payload_json}|{status}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def log(
        self,
        action: str,
        target: str,
        actor: str = "assistant",
        payload: Optional[Dict[str, Any]] = None,
        status: str = "success",
    ) -> AuditEntry:
        """Appends an immutable entry to the cryptographic audit trail."""
        self.config.ensure_storage_dir()
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_data = payload or {}
        payload_json = json.dumps(payload_data, sort_keys=True)

        current_hash = self._compute_hash(
            prev_hash=self._last_hash,
            seq=self._seq,
            timestamp=timestamp,
            actor=actor,
            action=action,
            target=target,
            payload_json=payload_json,
            status=status,
        )

        entry = AuditEntry(
            seq=self._seq,
            timestamp=timestamp,
            actor=actor,
            action=action,
            target=target,
            payload=payload_data,
            status=status,
            prev_hash=self._last_hash,
            current_hash=current_hash,
        )

        # Append to log file
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

        self._last_hash = current_hash
        self._seq += 1
        return entry

    def read_entries(self, limit: int = 100) -> List[AuditEntry]:
        """Reads recent audit log entries."""
        if not self.log_file.exists():
            return []

        entries: List[AuditEntry] = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    entries.append(
                        AuditEntry(
                            seq=data["seq"],
                            timestamp=data["timestamp"],
                            actor=data["actor"],
                            action=data["action"],
                            target=data["target"],
                            payload=data["payload"],
                            status=data["status"],
                            prev_hash=data["prev_hash"],
                            current_hash=data["current_hash"],
                        )
                    )
                except Exception:
                    continue

        return entries[-limit:]

    def verify_integrity(self) -> Tuple[bool, str, int]:
        """Verifies the complete SHA-256 chain from genesis to head.

        Returns (is_valid, message, num_entries_verified).
        """
        if not self.log_file.exists():
            return True, "Audit log is empty (valid).", 0

        expected_prev = self.GENESIS_HASH
        expected_seq = 0
        count = 0

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except Exception as e:
                    return False, f"Malformed JSON on line {line_no}: {str(e)}", count

                # Verify sequence
                if entry["seq"] != expected_seq:
                    return False, (
                        f"Sequence break at line {line_no}: expected seq {expected_seq}, "
                        f"got {entry['seq']}"
                    ), count

                # Verify previous hash link
                if entry["prev_hash"] != expected_prev:
                    return False, (
                        f"Cryptographic link broken at seq {entry['seq']}: "
                        f"expected prev_hash {expected_prev}, got {entry['prev_hash']}"
                    ), count

                # Recompute current hash
                payload_json = json.dumps(entry["payload"], sort_keys=True)
                calc_hash = self._compute_hash(
                    prev_hash=entry["prev_hash"],
                    seq=entry["seq"],
                    timestamp=entry["timestamp"],
                    actor=entry["actor"],
                    action=entry["action"],
                    target=entry["target"],
                    payload_json=payload_json,
                    status=entry["status"],
                )

                if calc_hash != entry["current_hash"]:
                    return False, (
                        f"Tamper detected at seq {entry['seq']}: "
                        f"computed hash {calc_hash} != stored hash {entry['current_hash']}"
                    ), count

                expected_prev = entry["current_hash"]
                expected_seq += 1
                count += 1

        return True, f"Cryptographic integrity verified across {count} audit records.", count
