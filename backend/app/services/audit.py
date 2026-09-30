import json
from pathlib import Path


class AuditService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def record(self, job_id: str, before: dict, after: dict, result: dict | None = None) -> str:
        artifact_dir = self.base_dir / job_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._write(artifact_dir / "before.json", before)
        self._write(artifact_dir / "after.json", after)
        self._write(artifact_dir / "result.json", result or {"before": before, "after": after})
        return str(artifact_dir)

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )