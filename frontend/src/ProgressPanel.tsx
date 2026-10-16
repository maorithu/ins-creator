import React from 'react';
import { AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react';

export interface TaskLogEntry {
  stage: string;
  service?: string;
  at: number;
}

export interface TaskProgress {
  task_id: string;
  title: string;
  status: 'waiting' | 'running' | 'done' | 'error' | 'unknown';
  percent: number;
  stage: string;
  service: string;
  detail?: string;
  elapsed_sec?: number;
  log: TaskLogEntry[];
  indeterminate?: boolean;
}

export function newTaskId(prefix = 't'): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

/** POST multipart form data with real upload progress (fetch() can't report upload progress). */
export function xhrUpload<T>(
  url: string,
  body: FormData,
  headers: Record<string, string>,
  onUploadProgress: (fraction: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onUploadProgress(ev.loaded / Math.max(1, ev.total));
    };
    xhr.upload.onload = () => onUploadProgress(1);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch (err) {
          reject(err);
        }
      } else {
        reject(new Error(xhr.responseText.slice(0, 200) || `HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(body);
  });
}

function formatElapsed(sec?: number): string {
  if (sec === undefined || sec === null) return '';
  if (sec < 60) return `${sec.toFixed(0)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

export function ProgressPanel({
  task,
  onDismiss,
}: {
  task: TaskProgress | null;
  onDismiss: () => void;
}) {
  if (!task) return null;
  const pct = Math.max(0, Math.min(100, task.percent || 0));
  const isDone = task.status === 'done';
  const isError = task.status === 'error';
  const isWaiting = task.status === 'waiting' || task.indeterminate;
  const recent = task.log.slice(-4, -1).reverse();

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 right-5 z-50 w-[380px] max-w-[calc(100vw-2.5rem)] rounded-xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10 p-4 space-y-2.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {isDone ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          ) : isError ? (
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          ) : (
            <Loader2 className="w-4 h-4 text-slate-700 animate-spin shrink-0" />
          )}
          <span className="text-sm font-semibold text-slate-900 truncate">{task.title}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-mono font-semibold text-slate-700 tabular-nums">
            {isWaiting && !isDone ? '—' : `${pct.toFixed(0)}%`}
          </span>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Hide progress"
            className="p-0.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
        {isWaiting && !isDone ? (
          <div className="h-full w-1/3 rounded-full bg-slate-400 animate-[progress-indeterminate_1.4s_ease-in-out_infinite]" />
        ) : (
          <div
            className={`h-full rounded-full transition-[width] duration-500 ease-out ${
              isError ? 'bg-rose-500' : isDone ? 'bg-emerald-500' : 'bg-slate-900'
            }`}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>

      <div className="space-y-1">
        <p className="text-xs text-slate-800 leading-snug">{task.stage}</p>
        {isError && task.detail && <p className="text-[11px] text-rose-600">{task.detail}</p>}
        <div className="flex items-center justify-between gap-2">
          {task.service ? (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100 truncate max-w-[270px]">
              via {task.service}
            </span>
          ) : (
            <span />
          )}
          {task.elapsed_sec !== undefined && (
            <span className="text-[10px] text-slate-400 font-mono shrink-0">
              {formatElapsed(task.elapsed_sec)}
            </span>
          )}
        </div>
      </div>

      {recent.length > 0 && !isDone && (
        <ul className="pt-1.5 border-t border-slate-100 space-y-0.5">
          {recent.map((entry, i) => (
            <li key={`${entry.at}-${i}`} className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="truncate">{entry.stage}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function useTaskRunner(setStatusMessage: (msg: string | null) => void) {
  const [task, setTask] = React.useState<TaskProgress | null>(null);
  const pollRef = React.useRef<number | null>(null);
  const hideRef = React.useRef<number | null>(null);
  const uploadRef = React.useRef<{ share: number; fraction: number }>({ share: 0, fraction: 0 });
  const startedAtRef = React.useRef<number>(0);

  const stopPolling = React.useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = React.useCallback(
    (taskId: string) => {
      stopPolling();
      pollRef.current = window.setInterval(async () => {
        try {
          const res = await fetch(`/api/progress/${encodeURIComponent(taskId)}`);
          if (!res.ok) return;
          const data = await res.json();
          setTask((prev) => {
            if (!prev || prev.task_id !== taskId || prev.status === 'done' || prev.status === 'error') return prev;
            const elapsed = (Date.now() - startedAtRef.current) / 1000;
            const { share, fraction } = uploadRef.current;
            if (data.status === 'unknown') {
              return {
                ...prev,
                elapsed_sec: elapsed,
                percent: share > 0 ? share * 100 * fraction : prev.percent,
              };
            }
            const serverPct = Number(data.percent) || 0;
            return {
              ...prev,
              status: data.status === 'running' ? 'running' : prev.status,
              indeterminate: false,
              percent: Math.max(prev.percent, share * 100 + (1 - share) * serverPct),
              stage: data.stage || prev.stage,
              service: data.service || prev.service,
              detail: data.detail,
              log: Array.isArray(data.log) ? data.log : prev.log,
              elapsed_sec: elapsed,
            };
          });
        } catch {
          /* transient polling errors are fine */
        }
      }, 450);
    },
    [stopPolling]
  );

  const finish = React.useCallback(
    (taskId: string, ok: boolean, message?: string) => {
      stopPolling();
      setTask((prev) =>
        prev && prev.task_id === taskId
          ? {
              ...prev,
              status: ok ? 'done' : 'error',
              percent: ok ? 100 : prev.percent,
              stage: ok ? message || 'Completed' : 'Failed',
              detail: ok ? prev.detail : message,
              indeterminate: false,
              elapsed_sec: (Date.now() - startedAtRef.current) / 1000,
            }
          : prev
      );
      if (hideRef.current) window.clearTimeout(hideRef.current);
      hideRef.current = window.setTimeout(
        () => setTask((prev) => (prev && prev.task_id === taskId ? null : prev)),
        ok ? 1600 : 8000
      );
    },
    [stopPolling]
  );

  /**
   * Runs `fn` while showing live progress. `fn` receives the task id (send it as the
   * `X-Task-Id` header) and an upload-progress callback (for XHR uploads).
   */
  const runTask = React.useCallback(
    async <T,>(
      title: string,
      initial: { stage: string; service: string; uploadShare?: number },
      fn: (taskId: string, onUpload: (fraction: number) => void) => Promise<T>,
      doneMessage?: string
    ): Promise<T> => {
      const taskId = newTaskId();
      if (hideRef.current) window.clearTimeout(hideRef.current);
      uploadRef.current = { share: initial.uploadShare || 0, fraction: 0 };
      startedAtRef.current = Date.now();
      setTask({
        task_id: taskId,
        title,
        status: 'running',
        percent: 0,
        stage: initial.stage,
        service: initial.service,
        log: [],
        elapsed_sec: 0,
      });
      startPolling(taskId);
      const onUpload = (fraction: number) => {
        uploadRef.current.fraction = fraction;
        setTask((prev) =>
          prev && prev.task_id === taskId && prev.status === 'running'
            ? {
                ...prev,
                percent: Math.max(prev.percent, (initial.uploadShare || 0) * 100 * fraction),
                stage: fraction < 1 ? `${initial.stage} (${Math.round(fraction * 100)}%)` : 'Upload complete — starting analysis…',
              }
            : prev
        );
      };
      try {
        const result = await fn(taskId, onUpload);
        finish(taskId, true, doneMessage);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        finish(taskId, false, msg);
        setStatusMessage(`${title} failed: ${msg.slice(0, 160)}`);
        throw err;
      }
    },
    [finish, setStatusMessage, startPolling]
  );

  /** Shows a "waiting for the user" state (e.g. Google Photos picker) bound to a server task id. */
  const showWaiting = React.useCallback(
    (taskId: string, title: string, stage: string, service: string) => {
      if (hideRef.current) window.clearTimeout(hideRef.current);
      uploadRef.current = { share: 0, fraction: 0 };
      startedAtRef.current = Date.now();
      setTask({
        task_id: taskId,
        title,
        status: 'waiting',
        indeterminate: true,
        percent: 0,
        stage,
        service,
        log: [],
        elapsed_sec: 0,
      });
      startPolling(taskId);
    },
    [startPolling]
  );

  const dismiss = React.useCallback(() => setTask(null), []);

  React.useEffect(
    () => () => {
      stopPolling();
      if (hideRef.current) window.clearTimeout(hideRef.current);
    },
    [stopPolling]
  );

  return { task, runTask, showWaiting, finish, dismiss };
}
