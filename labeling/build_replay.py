"""
生成可视化标注页面：拖动时间线看代码回放，点击标注"该弹/不该弹"。

输出: sessions/SID_XXXXX_label.html — 浏览器打开即可标注
汇总: data/labels_visual.csv — 所有标注汇总
"""
import os, json, re, base64, random
import pandas as pd
import numpy as np
import pymysql

ROOT = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(os.path.dirname(ROOT), "data", "export")
SESSIONS_DIR = os.path.join(ROOT, "sessions")
LABELS_FILE = os.path.join(ROOT, "data", "labels_visual.csv")
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

SAMPLE_SIZE = 50  # 生成 50 个 session 的页面

IGNORE_KEYS = {
    "Control","Shift","Alt","Meta","CapsLock","Escape","Tab",
    "ArrowUp","ArrowDown","ArrowLeft","ArrowRight",
    "Home","End","PageUp","PageDown","Insert","Delete",
    "F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
    "Dead","Process","NumLock","ScrollLock","Pause"
}
DELETE_KEYS = {"Backspace"}

HTML_TEMPLATE = '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Label SID={sid}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:monospace;background:#1e1e1e;color:#d4d4d4;display:flex;flex-direction:column;height:100vh}}
#top{{padding:12px 16px;background:#252526;border-bottom:1px solid#3e3e3e;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
#top span{{color:#888;font-size:13px}}
#top .judge{{font-weight:bold;font-size:14px}}
#top .judge.AC{{color:#4ec9b0}}.judge.WA{{color:#f44747}}.judge.CE{{color:#dcdcaa}}.judge.TLE{{color:#569cd6}}
#code{{flex:1;padding:16px;overflow-y:auto;white-space:pre-wrap;font-size:14px;line-height:1.6}}
#code .added{{background:#1b3a1b;border-radius:2px}}
#bottom{{padding:10px 16px;background:#252526;border-top:1px solid#3e3e3e}}
#slider{{width:100%;height:24px;cursor:pointer;accent-color:#007acc}}
#controls{{display:flex;gap:8px;margin-top:8px;align-items:center}}
button{{padding:8px 16px;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:bold}}
.btn-yes{{background:#22863a;color:white}}
.btn-no{{background:#6a737d;color:white}}
.btn-skip{{background:#444;color:#aaa}}
.btn-save{{background:#007acc;color:white}}
#labels{{flex:1;text-align:right;font-size:12px;color:#888}}
#timeline{{display:flex;gap:1px;height:20px;margin-top:4px}}
.tick{{flex:1;min-width:1px;background:#444;border-radius:1px}}
.tick.active{{background:#007acc}}
</style></head><body>
<div id=top>
  <span>SID={sid}</span><span>PID={pid}</span><span class="judge {judge_cls}">{judge}</span>
  <span>{total_keys} keys, {duration}s, ~{kpm} kpm</span>
  <span>Problem: {pname}</span>
</div>
<div id=code></div>
<div id=bottom>
  <input type=range id=slider min=0 max={max_idx} value=0 step=1>
  <div id=timeline>{timeline}</div>
  <div id=controls>
    <button class=btn-yes onclick=mark(1)>[1] 该弹</button>
    <button class=btn-no onclick=mark(0)>[0] 不该弹</button>
    <button class=btn-skip onclick=mark(-1)>跳过</button>
    <span style=color:#888;font-size:12px>Keyboard: ← → to scrub, Y=该弹 N=不该弹</span>
    <span id=labels></span>
  </div>
</div>
{submitted}
<script>
const snapshots = {snapshots_json};
const total = snapshots.length;
let labels = [];
let current = 0;

function show(i) {{
  current = Math.max(0, Math.min(total-1, i));
  document.getElementById('slider').value = current;
  document.getElementById('code').innerHTML = snapshots[current].code;
}}

document.getElementById('slider').oninput = function() {{ show(parseInt(this.value)); }};

document.onkeydown = function(e) {{
  if (e.target.tagName === 'INPUT') return;
  if (e.key === 'ArrowRight') show(current + 10);
  if (e.key === 'ArrowLeft') show(current - 10);
  if (e.key === 'y' || e.key === 'Y') mark(1);
  if (e.key === 'n' || e.key === 'N') mark(0);
}};

function mark(v) {{
  const idx = Math.round(current / step * step);
  labels.push({{idx, label:v, time:snapshots[current].time, code:snapshots[current].code.substring(0,200)}});
  localStorage.setItem('labels_{sid}', JSON.stringify(labels));
  document.getElementById('labels').textContent = labels.length + ' labels';
}}

function save() {{
  const blob = new Blob([JSON.stringify(labels)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'labels_{sid}.json';
  a.click();
}}

function load() {{
  const saved = localStorage.getItem('labels_{sid}');
  if (saved) {{ labels = JSON.parse(saved); document.getElementById('labels').textContent = labels.length + ' labels'; }}
}}

load();
show(0);
</script></body></html>'''


def parse_time(s):
    s = re.sub(r':(\d+)$', r'.\1', str(s))
    for f in ["%Y/%m/%d %H:%M:%S.%f","%m/%d/%Y, %I:%M:%S %p.%f","%Y-%m-%d %I:%M:%S %p.%f","%d/%m/%Y, %H:%M:%S.%f"]:
        try: return pd.Timestamp(s, format=f)
        except: pass
    return None


def replay_code(keys):
    """从按键序列重建代码（每步存快照）"""
    snapshots = []
    code = ""
    for i, k in enumerate(keys):
        if k in IGNORE_KEYS: continue
        if k in DELETE_KEYS: code = code[:-1] if code else ""
        elif k == "Enter": code += "\n"
        elif k == " " or k == "Space": code += " "
        elif len(k) == 1: code += k

        if i % 3 == 0:  # 每 3 个有效按键存一次快照
            snapshots.append(code)
    if not snapshots or snapshots[-1] != code:
        snapshots.append(code)
    return snapshots


def code_to_html(code):
    """代码转 HTML，高亮最近添加的字符"""
    if not code: return ""
    escaped = code.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    lines = escaped.split("\n")
    html_lines = []
    for line in lines:
        line = line.replace("  "," &nbsp;")
        if not line: line = "&nbsp;"
        html_lines.append(line)
    return "<br>".join(html_lines)


def build_timeline_html(snapshots, step):
    """生成时间线小色条"""
    n = len(snapshots) // step
    ticks = ['<div class="tick"></div>'] * min(n, 200)
    return "".join(ticks)


def main():
    # 随机选 50 个 session
    print("Loading session list...")
    all_sids = []
    for batch in range(1, 200):
        fp = os.path.join(EXPORT_DIR, f"key_action_batch_{batch:03d}.csv")
        if not os.path.exists(fp): break
        df = pd.read_csv(fp)
        all_sids.extend(df["solution_id"].tolist())
    print(f"Total sessions: {len(all_sids)}")

    random.seed(42)
    selected = random.sample(all_sids, min(SAMPLE_SIZE, len(all_sids)))

    # 获取判题结果和题目名
    conn = pymysql.connect(host="122.207.108.6", port=53306,
                           user="root", password=os.environ.get("OJ_DB_PASSWORD", ""),
                           database="csuoj_db", charset="utf8mb4",
                           connect_timeout=10, read_timeout=60)
    cur = conn.cursor()
    judges = {}
    pnames = {}
    for i in range(0, len(selected), 500):
        chunk = selected[i:i+500]
        ph = ",".join(["%s"] * len(chunk))
        cur.execute(f"SELECT id, result, problem_id FROM solution WHERE id IN ({ph})", chunk)
        for r in cur.fetchall():
            labels = {4:"AC",5:"PE",6:"WA",7:"TLE",8:"MLE",9:"OLE",10:"NoData",11:"CE",13:"RE"}
            judges[r[0]] = labels.get(r[1], "?")
            pids = set()
            pids.add(r[2])
            judges[r[0]] = (judges.get(r[0], "?"), r[2])
    conn.close()

    n_built = 0
    for sid in selected:
        # 加载 session
        downs = None
        for batch in range(1, 200):
            fp = os.path.join(EXPORT_DIR, f"key_action_batch_{batch:03d}.csv")
            if not os.path.exists(fp): break
            df = pd.read_csv(fp)
            m = df[df["solution_id"] == sid]
            if len(m) == 0: continue
            actions = json.loads(m.iloc[0]["action"])
            downs = []
            for a in actions:
                if not isinstance(a, dict): continue
                ts = parse_time(a["time"])
                if ts is None: continue
                downs.append((a.get("key","?"), ts))
            break
        if downs is None or len(downs) < 20: continue

        # 回放
        keys = [k for k, t in downs]
        snapshots = replay_code(keys)
        if len(snapshots) < 10: continue

        judge_info = judges.get(sid, ("?", 0))
        judge = judge_info[0] if isinstance(judge_info, tuple) else judge_info
        pid = judge_info[1] if isinstance(judge_info, tuple) else 0

        # 找提交代码
        code_html = ""
        try:
            conn2 = pymysql.connect(host="122.207.108.6", port=53306,
                user="root", password=os.environ.get("OJ_DB_PASSWORD", ""), database="csuoj_db",
                charset="utf8mb4", connect_timeout=5, read_timeout=10)
            cur2 = conn2.cursor()
            cur2.execute(f"SELECT code FROM source_code WHERE solution_id={sid}")
            r = cur2.fetchone()
            if r and r[0]:
                code_html = f'<div style="margin-top:16px;padding:8px;background:#252526;border-radius:4px"><b>Submitted Code:</b><pre style="font-size:12px;max-height:150px;overflow:auto">{code_to_html(r[0])}</pre></div>'
            conn2.close()
        except: pass

        # 生成快照 JSON（每 step 个取一个，控制文件大小）
        step = max(1, len(snapshots) // 300)
        snap_list = []
        for i in range(0, len(snapshots), step):
            snap_list.append({"idx": i, "time": f"{i*0.3:.0f}s", "code": code_to_html(snapshots[i])})

        total_keys = len(keys)
        duration = len(snapshots) * 0.3  # 估计

        html = HTML_TEMPLATE.format(
            sid=sid, pid=pid, judge=judge,
            judge_cls=judge if judge in ("AC","WA","CE","TLE","PE") else "",
            total_keys=total_keys, duration=f"{duration:.0f}",
            kpm=f"{total_keys/max(duration,1)*60:.0f}",
            pname=f"PID-{pid}",
            max_idx=len(snap_list)-1,
            timeline=build_timeline_html(snapshots, step),
            snapshots_json=json.dumps(snap_list, ensure_ascii=False),
            submitted=code_html,
            step=step
        )

        out = os.path.join(SESSIONS_DIR, f"label_{sid}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        n_built += 1
        if n_built % 10 == 0:
            print(f"  {n_built} pages built...")

    print(f"\nDone. {n_built} pages in: {SESSIONS_DIR}")
    print(f"Open any .html file in browser to start labeling.")
    print(f"Labels saved in browser localStorage. Click 'Save' to download as JSON.")


if __name__ == "__main__":
    main()
