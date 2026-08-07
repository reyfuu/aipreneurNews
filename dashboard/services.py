from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    total_seconds = max(0, int(seconds))
    minutes = total_seconds // 60
    remaining = total_seconds % 60
    return f"{minutes:02d}:{remaining:02d}"


def _compute_task_elapsed(task: dict) -> float:
    started = _to_datetime(task.get("started_at"))
    if not started:
        return 0.0
    finished = task.get("finished_at")
    end = _to_datetime(finished) if finished else datetime.now(timezone.utc)
    if end is None:
        return 0.0
    return max(0.0, (end - started).total_seconds())


def _set_job_state(task_id: str, **updates: object) -> None:
    with _lock:
        job = _jobs.get(task_id)
        if job is None:
            return
        job.update(updates)


_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _snapshot_jobs() -> list[dict]:
    with _lock:
        return sorted(_jobs.values(), key=lambda item: item["created_at"], reverse=True)


def start_pipeline_task(*, skip_upload: bool = False, run_date: str | None = None) -> str:
    task_id = uuid.uuid4().hex
    job = {
        "task_id": task_id,
        "status": "queued",
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "message": "Menunggu slot worker.",
        "phase": "queued",
        "progress": 0,
        "updated_at": _now_iso(),
        "skip_upload": skip_upload,
        "run_date": run_date,
        "result": None,
        "error": None,
    }
    with _lock:
        _jobs[task_id] = job

    thread = threading.Thread(
        target=_run_pipeline_task,
        args=(task_id,),
        kwargs={"skip_upload": skip_upload, "run_date": run_date},
        daemon=True,
    )
    thread.start()
    return task_id


def _run_pipeline_task(task_id: str, *, skip_upload: bool, run_date: Optional[str]) -> None:
    def report_progress(message: str, phase: str, progress: int | None) -> None:
        _set_job_state(
            task_id,
            status="running",
            started_at=_jobs.get(task_id, {}).get("started_at") or _now_iso(),
            updated_at=_now_iso(),
            message=message,
            phase=phase,
            progress=progress,
        )

    _set_job_state(task_id, status="running", started_at=_now_iso(), message="Pipeline dijalankan.", phase="starting", progress=10, updated_at=_now_iso())

    try:
        from src.main import run_pipeline

        result = run_pipeline(skip_upload=skip_upload, run_date=run_date, on_progress=report_progress)
        with _lock:
            now = _now_iso()
            _jobs[task_id]["status"] = "finished"
            _jobs[task_id]["finished_at"] = now
            _jobs[task_id]["updated_at"] = now
            _jobs[task_id]["message"] = "Pipeline selesai."
            _jobs[task_id]["phase"] = "done"
            _jobs[task_id]["progress"] = 100
            _jobs[task_id]["result"] = result
            return
    except Exception as exc:  # pragma: no cover
        now = _now_iso()
        with _lock:
            _jobs[task_id]["status"] = "failed"
            _jobs[task_id]["finished_at"] = now
            _jobs[task_id]["updated_at"] = now
            _jobs[task_id]["message"] = "Pipeline gagal."
            _jobs[task_id]["phase"] = _jobs[task_id].get("phase", "error")
            _jobs[task_id]["progress"] = _jobs[task_id].get("progress", 0)
            _jobs[task_id]["error"] = str(exc)


def get_task(task_id: str) -> dict | None:
    with _lock:
        raw = _jobs.get(task_id)
        if raw is None:
            return None
        task = dict(raw)
    elapsed = _compute_task_elapsed(task)
    task["elapsed_seconds"] = round(elapsed, 2)
    task["elapsed"] = _format_elapsed(task["elapsed_seconds"])
    return task


def get_tasks(limit: int = 20) -> list[dict]:
    tasks = _snapshot_jobs()
    return tasks[:limit]


def get_outputs(limit: int = 20) -> list[dict[str, object]]:
    output_root = Path("output")
    if not output_root.exists():
        return []

    folders = [item for item in output_root.iterdir() if item.is_dir() and item.name[0].isdigit()]
    records = []
    for folder in sorted(folders, key=lambda item: item.name, reverse=True):
        record = {
            "date": folder.name,
            "script_file": _build_file_entry(folder / "script.json"),
            "ig_caption_file": _build_file_entry(folder / "ig_caption.txt"),
            "voiceover": _build_file_entry(folder / "voiceover.mp3"),
            "final_video": _build_file_entry(folder / "final_video.mp4"),
            "thumbnail": _build_file_entry(folder / "thumbnail.png"),
        }
        records.append(record)
        if len(records) >= limit:
            break
    return records


def _build_file_entry(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return {
        "path": str(path),
        "name": path.name,
        "size": path.stat().st_size,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
    }
