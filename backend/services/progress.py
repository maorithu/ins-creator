"""
Lightweight, thread-safe progress tracker for long-running studio tasks
(importing, analyzing, music cue extraction, timeline sync, AI copywriting, MP4 rendering).

Usage inside a (sync) endpoint:

    with track(task_id, "Generating Reel & Post"):
        update(5, "Loading media", service="Local media cache")
        with scope(10, 60):              # nested work reports 0-100 mapped into 10-60
            for i, item in enumerate(items):
                update(100 * i / len(items), f"Analyzing {item}", service="OpenCV")

The frontend sends an `X-Task-Id` header and polls `GET /api/progress/{task_id}`.
"""
from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional, Tuple

_LOCK = threading.Lock()
_TASKS: Dict[str, Dict[str, object]] = {}
_MAX_TASKS = 200

_current_task: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ins_creator_progress_task", default=None
)
_current_range: contextvars.ContextVar[Tuple[float, float]] = contextvars.ContextVar(
    "ins_creator_progress_range", default=(0.0, 100.0)
)


def _prune_locked() -> None:
    if len(_TASKS) <= _MAX_TASKS:
        return
    oldest = sorted(_TASKS.items(), key=lambda kv: float(kv[1].get("updated_at", 0.0)))
    for tid, _ in oldest[: len(_TASKS) - _MAX_TASKS]:
        _TASKS.pop(tid, None)


def start(task_id: str, title: str) -> None:
    now = time.time()
    with _LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "title": title,
            "status": "running",
            "percent": 0.0,
            "stage": "Starting…",
            "service": "",
            "detail": "",
            "started_at": now,
            "updated_at": now,
            "log": [],
        }
        _prune_locked()


def update(
    percent: Optional[float] = None,
    stage: Optional[str] = None,
    service: Optional[str] = None,
    detail: Optional[str] = None,
    task_id: Optional[str] = None,
) -> None:
    """Report progress. `percent` is relative (0-100) to the current `scope`."""
    tid = task_id or _current_task.get()
    if not tid:
        return
    lo, hi = _current_range.get()
    with _LOCK:
        task = _TASKS.get(tid)
        if task is None or task.get("status") != "running":
            return
        if percent is not None:
            absolute = lo + (hi - lo) * max(0.0, min(100.0, float(percent))) / 100.0
            # Never move backwards; keep a little headroom for the final "done"
            task["percent"] = round(max(float(task["percent"]), min(99.0, absolute)), 1)
        if stage is not None and stage != task.get("stage"):
            log: List[Dict[str, object]] = task["log"]  # type: ignore[assignment]
            log.append(
                {
                    "stage": stage,
                    "service": service if service is not None else task.get("service", ""),
                    "at": round(time.time() - float(task["started_at"]), 1),
                }
            )
            if len(log) > 12:
                del log[: len(log) - 12]
            task["stage"] = stage
        if service is not None:
            task["service"] = service
        if detail is not None:
            task["detail"] = detail
        task["updated_at"] = time.time()


def finish(task_id: str, stage: str = "Done", status: str = "done", detail: str = "") -> None:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return
        task["status"] = status
        if status == "done":
            task["percent"] = 100.0
        task["stage"] = stage
        if detail:
            task["detail"] = detail
        task["updated_at"] = time.time()


def get(task_id: str) -> Dict[str, object]:
    with _LOCK:
        task = _TASKS.get(task_id)
        if task is None:
            return {"task_id": task_id, "status": "unknown", "percent": 0.0}
        snapshot = dict(task)
        snapshot["log"] = list(task.get("log", []))  # type: ignore[arg-type]
        snapshot["elapsed_sec"] = round(time.time() - float(task["started_at"]), 1)
        return snapshot


@contextmanager
def track(task_id: Optional[str], title: str) -> Iterator[None]:
    """Binds `task_id` to the current thread/context for nested `update()` calls."""
    if not task_id:
        yield
        return
    already_running = get(task_id).get("status") == "running"
    if not already_running:
        start(task_id, title)
    tok_task = _current_task.set(task_id)
    tok_range = _current_range.set((0.0, 100.0))
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        finish(task_id, stage="Failed", status="error", detail=str(exc)[:240])
        raise
    else:
        finish(task_id, stage="Completed")
    finally:
        _current_task.reset(tok_task)
        _current_range.reset(tok_range)


@contextmanager
def scope(lo: float, hi: float) -> Iterator[None]:
    """Maps nested 0-100 progress into [lo, hi] of the enclosing scope."""
    parent_lo, parent_hi = _current_range.get()
    span = parent_hi - parent_lo
    new_range = (parent_lo + span * lo / 100.0, parent_lo + span * hi / 100.0)
    tok = _current_range.set(new_range)
    try:
        yield
    finally:
        _current_range.reset(tok)
