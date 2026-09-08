"""
LLM 零样本判断实验：对每条标注候选问 LLM "该不该弹"，对比人工标签。
使用 DeepSeek API (和 oj_ai_svr 同一配置)
"""
import os, json, time
import pandas as pd
from openai import OpenAI

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CANDIDATES = os.path.join(DATA_DIR, "candidates_200.csv")
LABELS = os.path.join(DATA_DIR, "labels.csv")
OUTPUT = os.path.join(DATA_DIR, "llm_results.csv")

# API config (same as oj_ai_svr/ai.yaml)
client = OpenAI(
    api_key=os.environ.get("OJ_LLM_API_KEY", ""),
    base_url="https://api.chat.csu.edu.cn/v1"
)
MODEL = "deepseek-v3"

PROMPT = """You are evaluating whether an AI tutor should proactively intervene while a student is coding on an Online Judge platform.

Student context:
- Problem: {problem_id} (Judge result: {judge})
- Trigger: {trigger_type} — {trigger_detail}
- Session: {total_keys} keystrokes over {duration_s} seconds (~{kpm} keys/min)

Key sequences around trigger:
- 10s before: {keys_10s_before}
- 10s after: {keys_10s_after}
- 30s before: {keys_30s_before}
- 30s after: {keys_30s_after}

Code state at trigger (reconstructed, may be incomplete):
```
{code_at_trigger}
```

Submitted code (final version):
```
{submitted_code_preview}
```

Based on this information, should the AI tutor proactively intervene at this moment?

Answer with ONLY one word: YES or NO. Do not explain."""


def main():
    cand = pd.read_csv(CANDIDATES)
    labels = pd.read_csv(LABELS)

    # Merge: only judge labeled samples (use solution_id + detail as key)
    cand["detail"] = cand["detail"].astype(str)
    labels["detail"] = labels["detail"].astype(str)
    # Drop label from cand, keep everything else
    cand_clean = cand.drop(columns=["label"], errors="ignore")
    # Keep only first match per solution_id+detail
    cand_clean = cand_clean.drop_duplicates(subset=["solution_id", "detail"])
    df = labels.merge(cand_clean, on=["solution_id", "type", "detail"], how="left", suffixes=("", "_cand"))

    print(f"{len(df)} labeled samples\n")

    results = []
    for idx, (_, row) in enumerate(df.iterrows()):
        # Build prompt
        kpm = int(row["total_keys"]) / max(float(row["duration_s"]), 1) * 60
        sub_preview = str(row.get("submitted_code", ""))[:800]
        code_at = str(row.get("code_at_trigger", ""))[:500]

        prompt = PROMPT.format(
            problem_id=int(row["problem_id"]),
            judge=row["judge"],
            trigger_type=row["type"],
            trigger_detail=row["detail"],
            total_keys=int(row["total_keys"]),
            duration_s=f"{float(row['duration_s']):.0f}",
            kpm=f"{kpm:.0f}",
            keys_10s_before=str(row.get("keys_10s_before", "")),
            keys_10s_after=str(row.get("keys_10s_after", "")),
            keys_30s_before=str(row.get("keys_30s_before", "")),
            keys_30s_after=str(row.get("keys_30s_after", "")),
            code_at_trigger=code_at if code_at.strip() else "(empty)",
            submitted_code_preview=sub_preview if sub_preview.strip() else "(none)",
        )

        # Call LLM with retry
        llm_yes = -1
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10, temperature=0.0
                )
                answer = resp.choices[0].message.content.strip().upper()
                llm_yes = 1 if "YES" in answer else 0
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(3)
                else:
                    print(f"  Error #{idx+1}: {str(e)[:80]}")
                    llm_yes = -1

        human_yes = int(row["label"])
        match = "✓" if llm_yes == human_yes else "✗"

        results.append({
            "solution_id": int(row["solution_id"]),
            "type": row["type"],
            "judge": row["judge"],
            "human_label": human_yes,
            "llm_label": llm_yes,
            "match": llm_yes == human_yes,
        })

        n = len(results)
        correct = sum(1 for r in results if r["match"])
        acc = correct / n * 100 if n > 0 else 0
        print(f"  #{idx+1}/{len(df)}: human={human_yes} llm={llm_yes} {match} | acc={acc:.0f}%")
        time.sleep(1.5)  # rate limit

    rdf = pd.DataFrame(results)
    rdf.to_csv(OUTPUT, index=False)

    valid = rdf[rdf["llm_label"] >= 0]
    print(f"\n{'='*50}")
    print(f"Total: {len(valid)}, Correct: {valid['match'].sum()}, "
          f"Accuracy: {valid['match'].mean()*100:.1f}%")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
