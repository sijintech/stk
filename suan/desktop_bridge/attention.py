"""Which "needs attention" items this person has viewed, per project (UX package U1).

Kept in the bridge state directory next to the recent-project history, never in the project: viewing
is a personal convenience, not project data, and does not change the editable revision.
ProjectSessions serializes access.
"""
import json
from pathlib import Path

from suan.runtime.common import atomic_json

MAX_KEYS_PER_PROJECT = 2000
MAX_BYTES = 4 * 1024 * 1024


class AttentionViews:
    def __init__(self, state_dir=None):
        self.path = Path(state_dir) / "attention-viewed.json" if state_dir is not None else None
        self.entries = None

    def _load(self):
        if self.entries is not None:
            return
        self.entries = {}
        try:
            if self.path is not None and self.path.exists():
                with self.path.open("rb") as stream:
                    raw = stream.read(MAX_BYTES + 1)
                data = json.loads(raw) if len(raw) <= MAX_BYTES else {}
                if isinstance(data, dict):
                    self.entries = {project: [key for key in keys if isinstance(key, str)][-MAX_KEYS_PER_PROJECT:]
                                    for project, keys in data.items() if isinstance(project, str) and isinstance(keys, list)}
        except (OSError, ValueError):
            self.entries = {}  # a damaged file only forgets what was viewed

    def viewed(self, project_id):
        self._load()
        return set(self.entries.get(project_id, ()))

    def mark(self, project_id, keys):
        self._load()
        known = self.entries.get(project_id, [])
        present = set(known)
        known = known + [key for key in keys if key not in present]
        self.entries[project_id] = known[-MAX_KEYS_PER_PROJECT:]
        if self.path is not None:
            atomic_json(self.path, self.entries)
        return len(keys)
