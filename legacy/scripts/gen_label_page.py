"""生成可视化标注页面：左边提交代码 + 右边编码活动时间线（含按键摘要）"""
import os, json, re, pandas as pd, pymysql, sys

EXPORT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "export")
OUT = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(OUT, exist_ok=True)
sid = int(sys.argv[1]) if len(sys.argv) > 1 else 1162776


def parse_time(s):
    s = re.sub(r':(\d+)$', r'.\1', str(s))
    for f in ['%Y/%m/%d %H:%M:%S.%f', '%m/%d/%Y, %I:%M:%S %p.%f',
              '%Y-%m-%d %I:%M:%S %p.%f', '%d/%m/%Y, %H:%M:%S.%f']:
        try: return pd.to_datetime(s, format=f)
        except: pass
    return None


# Load session
print(f"Loading SID={sid}...")
for b in range(1, 200):
    fp = os.path.join(EXPORT, f"key_action_batch_{b:03d}.csv")
    if not os.path.exists(fp): break
    df = pd.read_csv(fp)
    m = df[df["solution_id"] == sid]
    if len(m) > 0:
        actions = json.loads(m.iloc[0]["action"])
        break

# Submitted code + judge
conn = pymysql.connect(host="122.207.108.6", port=53306, user="root",
                       password=os.environ.get("OJ_DB_PASSWORD", ""), database="csuoj_db",
                       charset="utf8mb4", connect_timeout=5, read_timeout=10)
cur = conn.cursor()
cur.execute(f"SELECT code FROM source_code WHERE solution_id={sid}")
submitted_code = (cur.fetchone() or [""])[0] or ""
cur.execute(f"SELECT result, problem_id FROM solution WHERE id={sid}")
sol = cur.fetchone()
RES = {4: "AC", 5: "PE", 6: "WA", 7: "TLE", 8: "MLE", 9: "OLE", 10: "NoData", 11: "CE", 13: "RE"}
judge = RES.get(sol[0], "?") if sol else "?"
pid = sol[1] if sol else 0
conn.close()

# Extract key events
events = []
t0 = None
for a in actions:
    if not isinstance(a, dict) or a.get("type") != "down": continue
    ts = parse_time(a["time"])
    if ts is None: continue
    if t0 is None: t0 = ts
    events.append({"k": str(a["key"]), "t": (ts - t0).total_seconds()})

total_dur = events[-1]["t"] if events else 1
total_keys = len(events)

# Group into bursts (gap > 30s)
bursts = []
bs = 0
for i in range(1, len(events)):
    if events[i]["t"] - events[i - 1]["t"] > 30:
        bursts.append({"start": events[bs]["t"], "end": events[i - 1]["t"], "events": events[bs:i]})
        bs = i
bursts.append({"start": events[bs]["t"], "end": events[-1]["t"], "events": events[bs:]})

# Build segments with key sequence summary
segments = []
prev_end = 0
for b in bursts:
    s_t, e_t, evs = b["start"], b["end"], b["events"]
    nk = len(evs)
    ks = [e["k"] for e in evs]
    backspaces = sum(1 for k in ks if k == "Backspace")
    enters = sum(1 for k in ks if k == "Enter")
    ctrls = sum(1 for k in ks if k == "Control")
    bs_pct = backspaces / max(nk, 1) * 100

    # Compress key sequence
    compressed = []
    prev_k = None; cnt = 0
    for k in ks:
        if k == prev_k: cnt += 1
        else:
            if cnt > 0:
                compressed.append(prev_k if cnt == 1 else f"{prev_k}x{cnt}")
            prev_k = k; cnt = 1
    if cnt > 0:
        compressed.append(prev_k if cnt == 1 else f"{prev_k}x{cnt}")
    seq = " → ".join(compressed[:40])

    # Gap
    if s_t - prev_end > 30:
        segments.append({"type": "gap", "label": f"Pause {s_t - prev_end:.0f}s"})
    prev_end = e_t

    # Color
    if nk == 0:
        color, h = "#333", 2
    elif bs_pct > 25:
        color, h = "#f44747", 14
    elif bs_pct > 10:
        color, h = "#e2b714", 10
    elif nk > 30:
        color, h = "#4ec9b0", 14
    else:
        color, h = "#555", 6

    segments.append({
        "type": "burst",
        "start": f"{s_t:.0f}s", "end": f"{e_t:.0f}s",
        "keys": nk, "bs": backspaces, "enter": enters, "ctrl": ctrls,
        "bs_pct": f"{bs_pct:.0f}%",
        "color": color, "width": max(4, nk * 3), "height": h,
        "seq": seq,
    })

segs_json = json.dumps(segments, ensure_ascii=False)
code_str = json.dumps(submitted_code, ensure_ascii=False)

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Label ''' + str(sid) + r'''</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Consolas, monospace; background: #1e1e1e; color: #d4d4d4; display: flex; height: 100vh; }
#left { width: 55%; display: flex; flex-direction: column; }
#code { flex: 1; padding: 14px; overflow-y: auto; font-size: 13px; line-height: 1.6; white-space: pre-wrap; background: #1a1a1a; }
#right { width: 45%; display: flex; flex-direction: column; border-left: 1px solid #3e3e3e; }
#tl { flex: 1; padding: 12px; overflow-y: auto; display: flex; flex-wrap: wrap; align-items: flex-start; align-content: flex-start; gap: 2px; }
.seg { border-radius: 3px; cursor: pointer; }
.seg:hover { outline: 2px solid white; z-index: 10; transform: scale(1.1); }
.seg.marked { outline: 2px solid #007acc; }
.gap { width: 100%; height: 6px; background: repeating-linear-gradient(90deg, #333 0, #333 4px, transparent 4px, transparent 8px); margin: 1px 0; font-size: 10px; color: #666; line-height: 16px; padding-left: 4px; }
#bar { padding: 10px 16px; background: #252526; border-top: 1px solid #3e3e3e; }
#btns { display: flex; gap: 6px; margin-top: 6px; align-items: center; flex-wrap: wrap; }
.btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px; color: white; }
.y { background: #22863a; } .n { background: #6a737d; } .s { background: #444; color: #aaa; }
#info { font-size: 11px; color: #888; margin-top: 4px; }
#detail { padding: 8px 12px; background: #2a2a2a; font-size: 11px; color: #aaa; min-height: 30px; word-break: break-all; }
.legend { display: flex; gap: 14px; font-size: 10px; margin-top: 4px; flex-wrap: wrap; }
.legend span { display: flex; align-items: center; gap: 4px; }
.legend .dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
</style>
</head>
<body>
<div id="left">
  <div style="padding:6px 14px;background:#333;font-size:12px">
    SID:''' + str(sid) + r''' PID:''' + str(pid) + r''' Judge:<b style="color:#f44747">''' + judge + r'''</b>
    | ''' + str(total_keys) + r''' keys ''' + f"{total_dur:.0f}" + r'''s | <span id="lc">0</span> labels
  </div>
  <div id="code"></div>
</div>
<div id="right">
  <div style="padding:6px 12px;background:#333;font-size:11px">Timeline — gaps = pauses &gt;30s. Click bar to see what was typed.</div>
  <div id="tl"></div>
  <div id="detail">Click any bar to see key sequence</div>
  <div id="bar">
    <div class="legend">
      <span><span class="dot" style="background:#4ec9b0"></span>Busy</span>
      <span><span class="dot" style="background:#555"></span>Slow</span>
      <span><span class="dot" style="background:#e2b714"></span>Mid BS</span>
      <span><span class="dot" style="background:#f44747"></span>High BS(>25%)</span>
      <span><span class="dot" style="background:#333;border:1px dashed #666"></span>Pause>30s</span>
    </div>
    <div id="btns">
      <button class="btn y" onclick="mark(1)">Y 该弹</button>
      <button class="btn n" onclick="mark(0)">N 不该弹</button>
      <button class="btn s" onclick="mark(-1)">S 跳过</button>
      <button onclick="saveLabels()" style="padding:6px 10px;background:#007acc;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">Save JSON</button>
    </div>
    <div id="info">Click bar, then press Y/N/S to label</div>
  </div>
</div>
<script>
var segs = ''' + segs_json + r''';
var labels = JSON.parse(localStorage.getItem("labels_''' + str(sid) + r'''") || "[]");
var active = -1;
var nBursts = 0;
for (var i = 0; i < segs.length; i++) { if (segs[i].type === "burst") nBursts++; }

function renderTL() {
  var h = "";
  for (var i = 0; i < segs.length; i++) {
    var s = segs[i];
    if (s.type === "gap") { h += "<div class=gap>" + s.label + "</div>"; continue; }
    var cls = "seg"; if (i === active) cls += " marked";
    for (var j = 0; j < labels.length; j++) { if (labels[j].seg === i) { cls += " marked"; break; } }
    var title = s.start + "-" + s.end + " | " + s.keys + " keys | BS=" + s.bs + "(" + s.bs_pct + ")";
    h += "<div class=\"" + cls + "\" style=\"width:" + s.width + "px;height:" + s.height + "px;background:" + s.color + "\" title=\"" + title + "\" onclick=\"clickSeg(" + i + ")\"></div>";
  }
  document.getElementById("tl").innerHTML = h;
}

function clickSeg(i) {
  if (segs[i].type === "gap") return;
  active = i; renderTL();
  var s = segs[i];
  document.getElementById("info").textContent = "[" + s.start + "-" + s.end + "] " + s.keys + "keys BS=" + s.bs + "(" + s.bs_pct + ") Enter=" + s.enter + " Ctrl=" + s.ctrl;
  document.getElementById("detail").textContent = "Keys: " + s.seq;
}

function mark(v) {
  if (active < 0) { alert("Click a bar first!"); return; }
  var s = segs[active];
  labels.push({seg: active, time: s.start + "-" + s.end, label: v, keys: s.keys, bs: s.bs, bs_pct: s.bs_pct});
  localStorage.setItem("labels_''' + str(sid) + r'''", JSON.stringify(labels));
  document.getElementById("lc").textContent = labels.length;
  document.getElementById("info").textContent = "Marked [" + s.start + "-" + s.end + "] as " + (v===1?"YES":v===0?"NO":"SKIP") + " | " + labels.length + " total";
  active = -1; renderTL();
}

document.onkeydown = function(e) {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if (e.key === "y" || e.key === "Y") mark(1);
  if (e.key === "n" || e.key === "N") mark(0);
  if (e.key === "s" || e.key === "S") mark(-1);
};

function saveLabels() {
  var b = new Blob([JSON.stringify(labels, null, 2)], {type: "application/json"});
  var a = document.createElement("a"); a.href = URL.createObjectURL(b);
  a.download = "labels_''' + str(sid) + r'''.json"; a.click();
}

document.getElementById("code").textContent = ''' + code_str + r''';
document.getElementById("lc").textContent = labels.length;
renderTL();
</script>
</body>
</html>'''

out_path = os.path.join(OUT, f"label_{sid}.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"Saved: {out_path}")
print(f"Keys: {total_keys}, Dur: {total_dur:.0f}s, Bursts: {len([s for s in segments if s['type']=='burst'])}")
