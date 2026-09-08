"""评估 causal_windows.csv，并输出可直接引用的离线实验摘要。"""
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def score(mask: pd.Series, labels: pd.Series) -> tuple[int, int, int, int, float, float, float]:
    hit = int(mask.sum())
    tp = int((mask & labels).sum())
    fp = hit - tp
    fn = int(labels.sum()) - tp
    precision = tp / hit if hit else 0.0
    recall = tp / int(labels.sum()) if int(labels.sum()) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return hit, tp, fp, fn, precision, recall, f1


def main() -> None:
    path = DATA / "causal_windows.csv"
    df = pd.read_csv(path)
    labels = df["label"].eq(1)
    print(f"input={path}")
    print(f"samples={len(df)}, positives={int(labels.sum())}, unique_window_id={df['window_id'].nunique()}")
    print("\nrule                         hit  tp  fp  fn  precision  recall    f1")
    rules = {
        "keys_30s < 5": df["keys_30s"] < 5,
        "keys_60s < 20": df["keys_60s"] < 20,
        "IDLE pause >= 30s": (df["type"] == "IDLE") & (df["current_idle_s"] >= 30),
    }
    for name, mask in rules.items():
        hit, tp, fp, fn, precision, recall, f1 = score(mask, labels)
        print(f"{name:<28s} {hit:>3d} {tp:>3d} {fp:>3d} {fn:>3d}"
              f" {precision:>9.1%} {recall:>7.1%} {f1:>7.1%}")

    print("\nby type (keys_30s < 5):")
    for kind, sub in df.groupby("type", sort=False):
        hit, tp, fp, fn, precision, recall, f1 = score(sub["keys_30s"] < 5, sub["label"].eq(1))
        print(f"{kind:<7s} n={len(sub):>3d} pos={int(sub['label'].sum()):>3d} "
              f"hit={hit:>3d} precision={precision:.1%} recall={recall:.1%} f1={f1:.1%}")

    print("\nquality checks:")
    print(f"duplicate_window_id={int(df['window_id'].duplicated().sum())}")
    print(f"trigger_definitions={df['trigger_definition'].value_counts().to_dict()}")
    print(f"future_event_leakage_rows={(df['current_idle_s'] < 0).sum()}")


if __name__ == "__main__":
    main()
