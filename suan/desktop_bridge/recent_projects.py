"""Bounded local project history, separate from project databases and open sessions.

The bridge owns its state-directory process lock; ProjectSessions serializes this store.
Listing history never opens/stat's a project, which may live on disconnected storage.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

from suan.runtime.common import atomic_json
from .protocol import BridgeError

LIMIT = 20
MAX_BYTES = 1024 * 1024


class RecentProjects:
    def __init__(self, state_dir=None):
        self.path = Path(state_dir) / "recent-projects.json" if state_dir is not None else None
        self.entries = None
        self.error = ""

    @staticmethod
    def _key(directory):
        # Directories are already resolved by ProjectSessions; normcase handles Windows aliases.
        return os.path.normcase(directory)

    def _load(self):
        if self.entries is not None:
            return
        try:
            if self.path is None or not self.path.exists():
                self.entries = []
                return
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("history exceeds its size limit")
            value = json.loads(raw)
            if (not isinstance(value, dict) or value.get("version") != 1
                    or set(value) != {"version", "projects"} or not isinstance(value["projects"], list)
                    or len(value["projects"]) > LIMIT):
                raise ValueError("unsupported history format")
            seen = set()
            for item in value["projects"]:
                if not isinstance(item, dict) or set(item) != {"id", "directory", "name", "last_opened"}:
                    raise ValueError("invalid history entry")
                if not all(isinstance(v, str) and v and len(v) <= 32768 for v in item.values()):
                    raise ValueError("invalid history text")
                if str(UUID(item["id"])) != item["id"] or not Path(item["directory"]).is_absolute():
                    raise ValueError("invalid project identity or directory")
                if len(item["name"]) > 1024:
                    raise ValueError("invalid project name")
                datetime.fromisoformat(item["last_opened"])
                key = self._key(item["directory"])
                if key in seen:
                    raise ValueError("duplicate project directory")
                seen.add(key)
            self.entries = value["projects"]
        except (OSError, ValueError, TypeError) as exc:
            raise BridgeError("unavailable", f"Cannot read recent projects: {exc}", retryable=False) from None

    def _save(self, entries):
        try:
            if self.path is not None:
                atomic_json(self.path, {"version": 1, "projects": entries})
        except OSError as exc:
            raise BridgeError("unavailable", f"Cannot save recent projects: {exc}", retryable=False) from None
        self.entries = entries
        self.error = ""

    def remember(self, info):
        # A preference write must never make a successfully created/opened project look failed.
        try:
            self._load()
            entry = {key: info[key] for key in ("id", "directory", "name")}
            entry["last_opened"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            key = self._key(entry["directory"])
            self._save(([entry] + [item for item in self.entries if self._key(item["directory"]) != key])[:LIMIT])
        except BridgeError as exc:
            self.error = exc.message

    def list(self):
        try:
            self._load()
        except BridgeError as exc:
            self.error = exc.message
        return {"projects": [dict(item) for item in self.entries or []], "warning": self.error}

    def forget(self, directory):
        self._load()
        key = self._key(directory)
        entries = [item for item in self.entries if self._key(item["directory"]) != key]
        removed = len(entries) != len(self.entries)
        self._save(entries)
        return {"removed": removed}
