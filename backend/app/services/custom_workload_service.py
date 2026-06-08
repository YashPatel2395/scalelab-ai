"""
CustomWorkloadService
─────────────────────
Handles upload, validation, storage, and subprocess execution of
user-provided Python workload files.

Execution model
───────────────
Each run is dispatched to custom_runner.py via subprocess with a hard
timeout. The runner imports the workload file, calls run(input_size, 1)
for the sequential baseline, then run(input_size, worker_count) for the
parallel measurement.

Security limitations (documented honestly)
──────────────────────────────────────────
- AST validation blocks common dangerous patterns but is not a sandbox.
- The subprocess has full filesystem and network access of the running user.
- Timeout is the only hard execution limit.
- Do not run workloads from untrusted sources in production.
- Future: replace subprocess with Docker-isolated sandbox.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.custom_workload import CustomWorkload
from app.workloads.custom_validator import validate_workload_file

logger = get_logger(__name__)

# Directory where uploaded workload files are stored.
# Resolved relative to this file so it works regardless of CWD.
_UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads" / "custom_workloads"

# Path to the runner script, adjacent to the backend package root.
_RUNNER_PATH = Path(__file__).resolve().parent.parent.parent / "custom_runner.py"


def _ensure_uploads_dir() -> None:
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class CustomWorkloadService:
    def __init__(self, db: Session):
        self.db = db

    # ── Upload + validate ─────────────────────────────────────────────────────

    def create(self, name: str, filename: str, source_code: str) -> CustomWorkload:
        """
        Validate and store a custom workload file.
        Returns the persisted CustomWorkload record.
        Raises ValueError with validation errors if AST check fails.
        """
        _ensure_uploads_dir()

        # Validate before touching the filesystem
        val = validate_workload_file(source_code)

        # Persist the record (even if validation failed, so errors are visible)
        record = CustomWorkload(
            name=name,
            filename=filename,
            file_path="",  # filled below
            status="available" if val.valid else "failed",
            validation_status="passed" if val.valid else "failed",
            validation_errors=val.errors or None,
            validation_warnings=val.warnings or None,
        )
        self.db.add(record)
        self.db.flush()  # obtain the UUID without committing

        if not val.valid:
            self.db.commit()
            raise ValueError(
                f"Workload validation failed: {'; '.join(val.errors)}"
            )

        # Write file to disk
        file_path = _UPLOADS_DIR / f"{record.id}.py"
        file_path.write_text(source_code, encoding="utf-8")
        record.file_path = str(file_path)

        self.db.commit()
        self.db.refresh(record)
        logger.info("Custom workload uploaded: %s (%s)", record.id, record.name)
        return record

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def list(self, limit: int = 100, offset: int = 0) -> list[CustomWorkload]:
        return (
            self.db.query(CustomWorkload)
            .order_by(CustomWorkload.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get(self, workload_id: str) -> CustomWorkload | None:
        return (
            self.db.query(CustomWorkload)
            .filter(CustomWorkload.id == workload_id)
            .first()
        )

    def delete(self, workload_id: str) -> bool:
        record = self.get(workload_id)
        if not record:
            return False
        # Remove file from disk if it exists
        if record.file_path and os.path.exists(record.file_path):
            try:
                os.remove(record.file_path)
            except OSError as exc:
                logger.warning("Could not delete workload file %s: %s", record.file_path, exc)
        self.db.delete(record)
        self.db.commit()
        return True

    # ── Execute ───────────────────────────────────────────────────────────────

    def run(
        self,
        workload_id: str,
        input_size: int,
        worker_count: int,
        iterations: int = 1,
        timeout_seconds: int = 60,
        enable_profiling: bool = False,
    ) -> dict:
        """
        Execute the workload in an isolated subprocess and return results.

        Returns a dict with keys:
            success, sequential_time, execution_time, speedup, efficiency,
            stdout, error, return_value
        """
        record = self.get(workload_id)
        if not record:
            raise KeyError(f"CustomWorkload '{workload_id}' not found")
        if record.validation_status != "passed":
            raise ValueError(
                f"Workload '{workload_id}' did not pass validation "
                f"(status={record.validation_status}). Fix the errors before running."
            )
        if not os.path.exists(record.file_path):
            raise FileNotFoundError(
                f"Workload file not found on disk: {record.file_path}. "
                "The workload may have been deleted."
            )

        cmd = [
            sys.executable,
            str(_RUNNER_PATH),
            "--file", record.file_path,
            "--input-size", str(input_size),
            "--workers", str(worker_count),
            "--iterations", str(iterations),
        ]
        if enable_profiling:
            cmd.append("--profile")

        logger.info(
            "[PROFILING_DEBUG] svc.run: workload=%s enable_profiling=%s --profile_in_cmd=%s cmd=%s",
            workload_id, enable_profiling, "--profile" in cmd, " ".join(cmd),
        )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(_UPLOADS_DIR),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Execution timed out after {timeout_seconds}s.",
                "traceback": None,
                "stdout": None,
                "sequential_time": None,
                "execution_time": None,
                "speedup": None,
                "efficiency": None,
                "return_value": None,
            }

        # Parse JSON from runner stdout
        try:
            result = json.loads(proc.stdout.strip())
        except (json.JSONDecodeError, ValueError):
            stderr_snippet = proc.stderr[-2048:] if proc.stderr else ""
            return {
                "success": False,
                "error": (
                    "Runner produced unexpected output. "
                    f"stderr: {stderr_snippet or '(empty)'}"
                ),
                "traceback": None,
                "stdout": proc.stdout[:2048] if proc.stdout else None,
                "sequential_time": None,
                "execution_time": None,
                "speedup": None,
                "efficiency": None,
                "return_value": None,
            }

        logger.info(
            "[PROFILING_DEBUG] svc.run result: success=%s returncode=%d "
            "result_keys=%s profiling_data_type=%s stderr_snippet=%s",
            result.get("success"), proc.returncode,
            list(result.keys()),
            type(result.get("profiling_data")).__name__,
            (proc.stderr or "")[-500:],
        )
        return result
