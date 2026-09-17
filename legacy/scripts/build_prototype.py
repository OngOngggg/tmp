"""Build a small causal window dataset and a standalone browser labeling page.

Outputs (all new files):
  labeling/data/prototype_windows.csv
  labeling/data/prototype_labels.csv
  labeling/sessions/prototype_label.html

The feature timestamp is the end of the window. No event at or after that
timestamp is used in any feature or replay string.
"""
from __future__ import annotations

import argparse
import os
import html
import json
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import pymysql
except ImportError:
    pymysql = None

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
DATA = ROOT / "data"
EXPORT = PROJECT / "data" / "export"
SESSIONS = ROOT / "sessions"
WINDOW_OUT = DATA / "prototype_windows.csv"
LABEL_OUT = DATA / "prototype_labels.csv"
PAGE_OUT = SESSIONS / "prototype_label.html"

MODIFIERS = {"Control", "Shift", "Alt", "Meta", "CapsLock", "Escape", "Tab", "Insert", "Delete"}
NAVIGATION = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"}
NON_TEXT_KEYS = MODIFIERS | NAVIGATION | {"Dead", "Process", "Unidentified"}


def parse_time(value: object) -> pd.Timestamp | None:
    text = re.sub(r":(\d+)$", r".\1", str(value))
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f",
                "%m/%d/%Y, %I:%M:%S %p.%f",
                "%Y-%m-%d %I:%M:%S %p.%f", "%d/%m/%Y, %H:%M:%S.%f"):
        try:
            return pd.to_datetime(text, format=fmt)
        except (ValueError, TypeError):
            pass
    return None


def build_index(export_dir: Path = EXPORT) -> dict[int, Path]:
    index: dict[int, Path] = {}
    files = sorted(set(export_dir.glob("key_action_batch_*.csv")) | set(export_dir.glob("key_action_clean.csv")))
    for no, path in enumerate(files, 1):
        try:
            ids = pd.read_csv(path, usecols=["solution_id"])["solution_id"]
        except Exception:
            continue
        for sid in ids.dropna().astype(int):
            index.setdefault(int(sid), path)
        if no % 20 == 0:
            print(f"indexed {no}/{len(files)} export files")
    return index


def load_events(path: Path, sid: int) -> list[dict]:
    frame = pd.read_csv(path)
    match = frame[frame["solution_id"].astype(int) == int(sid)]
    if match.empty:
        return []
    try:
        actions = json.loads(match.iloc[0]["action"])
    except (TypeError, json.JSONDecodeError):
        return []
    events = []
    for action in actions:
        if not isinstance(action, dict) or str(action.get("type", "")).lower() != "down":
            continue
        ts = parse_time(action.get("time"))
        if ts is None:
            continue
        events.append({"key": str(action.get("key", "?")), "time": ts,
                       "row": int(action.get("row", 0) or 0),
                       "column": int(action.get("column", 0) or 0)})
    events.sort(key=lambda x: x["time"])
    for i, event in enumerate(events):
        event["event_index"] = i
        event["interval_s"] = (event["time"] - events[i - 1]["time"]).total_seconds() if i else 0.0
    return events


def compress(keys: list[str], limit: int = 100) -> str:
    groups = []
    previous = None
    count = 0
    for key in keys:
        if key == previous:
            count += 1
        else:
            if previous is not None:
                groups.append(previous if count == 1 else f"{previous}x{count}")
            previous, count = key, 1
    if previous is not None:
        groups.append(previous if count == 1 else f"{previous}x{count}")
    return " -> ".join(groups[:limit])


def clipboard_ops(part: list[dict]) -> int:
    """Count likely Ctrl/Cmd-C/V operations from nearby modifier events."""
    count = 0
    for i, event in enumerate(part):
        if event["key"].lower() not in {"c", "v"}:
            continue
        recent = part[max(0, i - 40):i]
        if any(x["key"] in {"Control", "Meta"} and
               (event["time"] - x["time"]).total_seconds() <= 2 for x in recent):
            count += 1
    return count


def activity_type(keys: list[str], clipboard_count: int) -> str:
    text_keys = [k for k in keys if k not in NON_TEXT_KEYS]
    printable = [k for k in text_keys if k not in {"Backspace", "Enter"}]
    modifiers = sum(k in MODIFIERS for k in keys)
    if clipboard_count and len(printable) <= clipboard_count:
        return "剪贴板操作"
    if keys and modifiers / len(keys) >= 0.5:
        return "修饰键占多数"
    if printable:
        return "持续输入"
    return "低活动"


def assist_recommendation(row: dict) -> tuple[str, str]:
    """Conservative human-review hint; never replaces the manual label."""
    idle = row.get("current_idle_s")
    idle = float(idle) if idle is not None else 0.0
    text30 = int(row.get("text_keys_30s", 0))
    text60 = int(row.get("text_keys_60s", 0))
    ctrl30 = int(row.get("control_30s", 0))
    clip30 = int(row.get("clipboard_ops_30s", 0))
    keys30 = int(row.get("keys_30s", 0))
    if clip30 > 0 or (keys30 > 0 and ctrl30 / keys30 >= 0.5):
        return "不建议弹", "最近主要是快捷键/剪贴板操作，不像持续编码"
    if idle >= 20 and text30 == 0:
        return "不建议弹", f"窗口结束前已空闲约 {idle:.0f} 秒，可能在读题或检查输出"
    if idle >= 10 and text60 <= 3:
        return "需要人工判断", f"近期输入很少且有约 {idle:.0f} 秒停顿，可能是阅读或思考"
    if text30 >= 3 and idle <= 5:
        return "可考虑弹", "最近仍有连续文本输入，且没有明显长时间停顿"
    return "需要人工判断", "活动信号不足，不能仅凭按键行为判断"


def replay(events: list[dict]) -> str:
    """Approximate editor text using the recorded row/column caret position.

    The action stream is not a source-code snapshot: it can miss key-up events,
    cursor moves, and modifier state. Positioning characters by the recorded
    caret coordinates is therefore more faithful than simply concatenating
    keys, while the UI labels the result as an approximation.
    """
    lines: dict[int, list[str]] = {}
    for event in events:
        key = event["key"]
        if key in MODIFIERS or key in NAVIGATION or key in {"Dead", "Process", "Unidentified"}:
            continue
        row = max(int(event.get("row", 0) or 0), 0)
        column = max(int(event.get("column", 0) or 0), 0)
        line = lines.setdefault(row, [])
        if key == "Backspace":
            if column > 0 and column - 1 < len(line):
                line[column - 1] = ""
            continue
        if key == "Enter":
            lines.setdefault(row + 1, [])
            continue
        char = " " if key in {" ", "Space"} else key if len(key) == 1 else ""
        if not char:
            continue
        while len(line) <= column:
            line.append(" ")
        line[column] = char
    if not lines:
        return ""
    last_row = max(lines)
    text = "\n".join("".join(lines.get(row, [])).rstrip() for row in range(last_row + 1))
    return text[-6000:]


def window_row(sid: int, meta: dict, events: list[dict], end: pd.Timestamp, ordinal: int) -> dict:
    before = [e for e in events if e["time"] < end]
    row = {"window_id": f"{sid}-w{ordinal:03d}", "solution_id": sid,
           "event_index": before[-1]["event_index"] if before else -1,
           "window_end_time": end.isoformat(), "problem_id": meta["problem_id"],
           "judge": meta["judge"], "duration_s": meta["duration_s"],
           "total_keys": meta["total_keys"], "key_summary": compress([e["key"] for e in before[-250:]]),
           "code_replay": replay(before)}
    for seconds in (5, 10, 30, 60, 120):
        start = end - pd.Timedelta(seconds=seconds)
        part = [e for e in before if start <= e["time"] < end]
        keys = [e["key"] for e in part]
        clipboard_count = clipboard_ops(part)
        # Only intervals with both endpoints inside this window are causal
        # window-local pauses; do not carry a pause across the left boundary.
        intervals = [
            (b["time"] - a["time"]).total_seconds()
            for a, b in zip(part, part[1:])
            if (b["time"] - a["time"]).total_seconds() > 0
        ]
        row[f"keys_{seconds}s"] = len(part)
        row[f"text_keys_{seconds}s"] = sum(k not in NON_TEXT_KEYS for k in keys)
        row[f"modifier_keys_{seconds}s"] = sum(k in MODIFIERS for k in keys)
        row[f"clipboard_ops_{seconds}s"] = clipboard_count
        row[f"activity_type_{seconds}s"] = activity_type(keys, clipboard_count)
        row[f"pause_count_{seconds}s"] = sum(x >= 2 for x in intervals)
        row[f"pause_total_{seconds}s"] = round(sum(x for x in intervals if x >= 2), 3)
        row[f"pause_p90_{seconds}s"] = round(float(np.percentile(intervals, 90)), 3) if intervals else 0.0
        row[f"backspace_{seconds}s"] = keys.count("Backspace")
        row[f"enter_{seconds}s"] = keys.count("Enter")
        row[f"control_{seconds}s"] = keys.count("Control")
        row[f"row_changes_{seconds}s"] = sum(a["row"] != b["row"] for a, b in zip(part, part[1:]))
        row[f"column_changes_{seconds}s"] = sum(a["column"] != b["column"] for a, b in zip(part, part[1:]))
    row["current_idle_s"] = round((end - before[-1]["time"]).total_seconds(), 3) if before else None
    row["assist_recommendation"], row["assist_reason"] = assist_recommendation(row)
    return row


def make_page(rows: list[dict], page_out: Path = PAGE_OUT) -> None:
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    template = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Prototype window labeling</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f4f6f8;color:#202124}.top{padding:12px 18px;background:#263238;color:white}.layout{display:grid;grid-template-columns:300px 1fr;min-height:calc(100vh - 58px)}#list{overflow:auto;background:#fff;border-right:1px solid #ddd}.item{padding:9px;border-bottom:1px solid #eee;cursor:pointer;font-size:12px}.item.active{background:#e3f2fd}.main{padding:16px;overflow:auto}.cards{display:flex;gap:8px;flex-wrap:wrap}.card{background:white;border:1px solid #ddd;border-radius:5px;padding:8px;min-width:130px}.code{white-space:pre-wrap;background:#202124;color:#e8eaed;padding:12px;border-radius:5px;max-height:360px;overflow:auto}.summary{white-space:pre-wrap;background:white;padding:10px;border-radius:5px;border:1px solid #ddd}.btn{padding:9px 16px;margin:4px;border:0;border-radius:4px;color:#fff;cursor:pointer}.yes{background:#188038}.no{background:#c5221f}.skip{background:#5f6368}.export{background:#1a73e8}.muted{color:#667085;font-size:12px}.hint{color:#586174;font-size:13px;line-height:1.6;background:#eef3f8;border-left:4px solid #1a73e8;padding:8px 10px}</style></head><body>
<div class="top"><b>Prototype window labeling</b> <span id="count"></span><button class="btn export" onclick="downloadCsv()">导出 prototype_labels.csv</button></div>
<div class="layout"><div id="list"></div><main class="main"><div id="detail">请选择左侧窗口</div></main></div>
<script>const rows=__ROWS__;let labels=JSON.parse(localStorage.getItem('prototype_labels')||'{}');let active=0;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function nextUnlabelled(){return rows.findIndex(r=>!labels[r.window_id])}
function renderList(){const pending=rows.map((r,i)=>({r,i})).filter(x=>!labels[x.r.window_id]);document.getElementById('list').innerHTML=pending.map(x=>{const r=x.r,i=x.i;return `<div class="item ${i===active?'active':''}" onclick="select(${i})"><b>${esc(r.window_id)}</b><br>SID ${r.solution_id} | event ${r.event_index}<br>${esc(r.window_end_time)}</div>`}).join('');document.getElementById('count').textContent=` 已完成 ${Object.keys(labels).length}/${rows.length}，待标注 ${pending.length}`}
function select(i){if(i<0){document.getElementById('detail').innerHTML='<h2>全部完成</h2><p class="hint">所有窗口都已标注。点击顶部按钮导出 prototype_labels.csv。</p>';renderList();return}active=i;const r=rows[i];const label=labels[r.window_id]?.label??'';document.getElementById('detail').innerHTML=`<h2>${esc(r.window_id)}</h2><div class="muted">solution_id=${r.solution_id} | event_index=${r.event_index} | window_end_time=${esc(r.window_end_time)} | problem=${esc(r.problem_id)} | judge=${esc(r.judge)}</div><p><button class="btn yes" onclick="mark(1)">1 该弹</button><button class="btn no" onclick="mark(0)">0 不该弹</button><button class="btn skip" onclick="mark(-1)">-1 跳过</button> 当前：${label}</p><h3>窗口特征</h3><p class="hint">每张卡片表示“窗口结束前向回看”的时间范围。例如 5s = 结束时间前 5 秒到结束时间这一段。keys 是全部按键数；文本键数排除了 Control/Shift 等修饰键；剪贴板操作是检测到 Control/Meta 与 C/V 的组合；pause 是停顿次数（相邻按键间隔至少 2 秒）；BS/Enter/Control 是对应按键次数；rowΔ/colΔ 是编辑器行号/列号变化次数。</p><div class="cards">${['5','10','30','60','120'].map(w=>`<div class="card"><b>向前 ${w} 秒</b><br>活动类型=${esc(r['activity_type_'+w+'s'])}<br>按键数=${r['keys_'+w+'s']}<br>文本键=${r['text_keys_'+w+'s']}<br>修饰键=${r['modifier_keys_'+w+'s']}<br>剪贴板操作=${r['clipboard_ops_'+w+'s']}<br>停顿=${r['pause_count_'+w+'s']} 次<br>退格=${r['backspace_'+w+'s']}<br>Enter=${r['enter_'+w+'s']}<br>Control=${r['control_'+w+'s']}<br>行变化=${r['row_changes_'+w+'s']}<br>列变化=${r['column_changes_'+w+'s']}</div>`).join('')}</div><h3>按键摘要</h3><div class="summary">${esc(r.key_summary)}</div><h3>代码回放（触发点之前，近似重建）</h3><p class="hint">这是根据按键和光标行列位置重建的参考文本，不等同于最终提交源码；若记录缺失或编辑器发生复杂操作，文本可能不完整。</p><pre class="code">${esc(r.code_replay)}</pre><h3>提交代码</h3><pre class="code">${esc(r.submitted_code||'未找到本地提交代码')}</pre>`;renderList()}
function mark(v){const r=rows[active];labels[r.window_id]={window_id:r.window_id,solution_id:r.solution_id,event_index:r.event_index,window_end_time:r.window_end_time,label:v};localStorage.setItem('prototype_labels',JSON.stringify(labels));const next=nextUnlabelled();renderList();select(next)}
function downloadCsv(){const cols=['window_id','solution_id','event_index','window_end_time','label'];const lines=[cols.join(',')];rows.forEach(r=>{if(labels[r.window_id])lines.push(cols.map(c=>JSON.stringify(labels[r.window_id][c]??'')).join(','))});const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8'}));a.download='prototype_labels.csv';a.click()}
renderList();select(nextUnlabelled());</script></body></html>'''
    page_out.parent.mkdir(parents=True, exist_ok=True)
    page_out.write_text(template.replace("__ROWS__", payload), encoding="utf-8")


def fetch_submissions(solution_ids: list[int]) -> dict[int, str]:
    """Read submitted code when the existing OJ database is reachable."""
    if pymysql is None or not solution_ids:
        return {}
    password = os.environ.get("OJ_DB_PASSWORD", "")
    if not password:
        dotenv = PROJECT / ".env"
        if dotenv.exists():
            for line in dotenv.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == "OJ_DB_PASSWORD":
                    password = value.strip().strip("\"'")
                    break
    try:
        conn = pymysql.connect(host="122.207.108.6", port=53306, user="root",
                               password=password, database="csuoj_db",
                               charset="utf8mb4", connect_timeout=5, read_timeout=20)
        result: dict[int, str] = {}
        with conn.cursor() as cur:
            for start in range(0, len(solution_ids), 200):
                chunk = solution_ids[start:start + 200]
                placeholders = ",".join(["%s"] * len(chunk))
                cur.execute(f"SELECT solution_id, code FROM source_code WHERE solution_id IN ({placeholders})", chunk)
                for sid, code in cur.fetchall():
                    result[int(sid)] = str(code or "")
        conn.close()
        return result
    except Exception as exc:
        print(f"submission_code_lookup=unavailable ({type(exc).__name__}: {exc})")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-sessions", type=int, default=100)
    parser.add_argument("--windows-per-session", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--events-dir", type=Path, default=EXPORT,
                        help="directory containing key_action_batch_*.csv or key_action_clean.csv")
    parser.add_argument("--sessions-file", type=Path, default=DATA / "clean_sessions.csv",
                        help="clean session CSV to sample from")
    parser.add_argument("--output-dir", type=Path, default=DATA,
                        help="directory for prototype_windows.csv, labels template, and HTML page")
    args = parser.parse_args()
    clean = pd.read_csv(args.sessions_file)
    # Accept the explicit names emitted by extract_clean_dataset.py while
    # retaining compatibility with the original clean_sessions.csv schema.
    if "total_keys" not in clean.columns and "event_count" in clean.columns:
        clean["total_keys"] = clean["event_count"]
    if "judge" not in clean.columns and "final_judge" in clean.columns:
        clean["judge"] = clean["final_judge"]
    clean = clean[(clean["duration_s"] >= 60) & (clean["total_keys"] >= 30)].drop_duplicates("solution_id")
    clean["solution_id"] = clean["solution_id"].astype(int)
    index = build_index(args.events_dir)
    candidates = clean[clean.solution_id.isin(index)].copy()
    rng = random.Random(args.seed)
    selected = rng.sample(candidates.solution_id.tolist(), min(args.n_sessions, len(candidates)))
    meta = candidates.set_index("solution_id").to_dict("index")
    rows = []
    for sid in selected:
        events = load_events(index[sid], sid)
        if len(events) < 30:
            continue
        start, end = events[0]["time"], events[-1]["time"]
        span = max((end - start).total_seconds(), 60)
        points = np.linspace(max(30, span * .2), max(30, span * .9), args.windows_per_session)
        for ordinal, offset in enumerate(points, 1):
            rows.append(window_row(sid, meta[sid], events, start + pd.Timedelta(seconds=float(offset)), ordinal))
    submissions = fetch_submissions(selected)
    for row in rows:
        row["submitted_code"] = submissions.get(int(row["solution_id"]), "")
    frame = pd.DataFrame(rows)
    DATA.mkdir(exist_ok=True); SESSIONS.mkdir(exist_ok=True)
    window_out = args.output_dir / "prototype_windows.csv"
    label_out = args.output_dir / "prototype_labels.csv"
    page_out = args.output_dir.parent / "sessions" / "prototype_label.html" if args.output_dir == DATA else args.output_dir / "prototype_label.html"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(window_out, index=False, encoding="utf-8-sig")
    label_out.write_text("window_id,solution_id,event_index,window_end_time,label\n", encoding="utf-8")
    make_page(frame.to_dict("records"), page_out)
    print(f"selected_sessions={len(selected)}")
    print(f"built_windows={len(frame)}")
    print(f"unique_window_id={frame.window_id.nunique()}")
    print(f"window_columns={len(frame.columns)}")
    print(f"submitted_code_rows={sum(bool(x) for x in frame['submitted_code'])}")
    print(f"windows={window_out}")
    print(f"labels_template={label_out}")
    print(f"label_page={page_out}")


if __name__ == "__main__":
    main()
