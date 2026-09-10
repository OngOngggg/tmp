"""Build causal submission context and post-hoc objective outcome labels.

Columns describing submissions before the current solution are causal context.
Own/next results and pair-level outcomes are evaluation-only fields and must
not be used as online trigger features.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "clean_oj"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, default=DEFAULT_DATA / "clean_sessions.csv")
    parser.add_argument("--timeline", type=Path, default=DEFAULT_DATA / "submission_timeline.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA / "session_submission_context.csv")
    args = parser.parse_args()

    sessions = pd.read_csv(args.sessions)
    timeline = pd.read_csv(args.timeline, parse_dates=["created_time"])
    sessions["solution_id"] = pd.to_numeric(sessions["solution_id"], errors="raise").astype("int64")
    for column in ("solution_id", "created_by", "problem_id", "result"):
        timeline[column] = pd.to_numeric(timeline[column], errors="coerce")
    timeline = timeline.dropna(subset=["solution_id", "created_by", "problem_id", "created_time"])
    timeline[["solution_id", "created_by", "problem_id"]] = timeline[
        ["solution_id", "created_by", "problem_id"]
    ].astype("int64")
    timeline = timeline.sort_values(
        ["created_by", "problem_id", "created_time", "solution_id"], kind="stable"
    ).reset_index(drop=True)

    grouped = timeline.groupby(["created_by", "problem_id"], sort=False, dropna=False)
    timeline["prior_submit_count"] = grouped.cumcount()
    timeline["last_known_judge_before"] = grouped["result"].shift(1)
    timeline["last_known_judge_name"] = grouped["result_name"].shift(1)
    timeline["prior_submit_time"] = grouped["created_time"].shift(1)
    timeline["time_since_prior_s"] = (
        timeline["created_time"] - timeline["prior_submit_time"]
    ).dt.total_seconds()
    timeline["next_submit_result_after"] = grouped["result"].shift(-1)
    timeline["next_submit_result_name"] = grouped["result_name"].shift(-1)
    timeline["next_submit_time"] = grouped["created_time"].shift(-1)
    timeline["time_to_next_s"] = (
        timeline["next_submit_time"] - timeline["created_time"]
    ).dt.total_seconds()

    timeline["pair_submission_count"] = grouped["solution_id"].transform("size")
    timeline["pair_has_ac"] = grouped["result"].transform(lambda values: values.eq(4).any())
    pair_first_is_ac = grouped["result"].transform("first").eq(4)
    timeline["pair_outcome"] = "fully_stuck"
    timeline.loc[timeline["pair_has_ac"], "pair_outcome"] = "breakthrough"
    timeline.loc[pair_first_is_ac, "pair_outcome"] = "immediate_success"
    timeline["ac_submit_index"] = timeline["prior_submit_count"].where(timeline["result"].eq(4))
    timeline["first_ac_submit_index"] = grouped["ac_submit_index"].transform("min")
    timeline["is_before_first_ac"] = (
        timeline["first_ac_submit_index"].notna()
        & (timeline["prior_submit_count"] < timeline["first_ac_submit_index"])
    )
    timeline["is_first_ac"] = (
        timeline["first_ac_submit_index"].notna()
        & (timeline["prior_submit_count"] == timeline["first_ac_submit_index"])
    )
    timeline["is_after_first_ac"] = (
        timeline["first_ac_submit_index"].notna()
        & (timeline["prior_submit_count"] > timeline["first_ac_submit_index"])
    )

    context_columns = [
        "solution_id",
        "created_time",
        "result",
        "result_name",
        "prior_submit_count",
        "last_known_judge_before",
        "last_known_judge_name",
        "prior_submit_time",
        "time_since_prior_s",
        "next_submit_result_after",
        "next_submit_result_name",
        "next_submit_time",
        "time_to_next_s",
        "pair_submission_count",
        "pair_has_ac",
        "pair_outcome",
        "first_ac_submit_index",
        "is_before_first_ac",
        "is_first_ac",
        "is_after_first_ac",
    ]
    context = timeline[timeline["solution_id"].isin(sessions["solution_id"])][context_columns].copy()
    context = context.rename(columns={
        "created_time": "submit_time",
        "result": "own_result",
        "result_name": "own_result_name",
    })
    if context["solution_id"].duplicated().any():
        raise RuntimeError("submission timeline contains duplicate solution_id rows")

    merged = sessions.merge(context, on="solution_id", how="left", validate="one_to_one")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.out, index=False, encoding="utf-8-sig")

    matched = int(merged["submit_time"].notna().sum())
    print(f"sessions={len(sessions):,} matched_context={matched:,}")
    print("pair_outcome_distribution:")
    print(merged["pair_outcome"].value_counts(dropna=False).to_string())
    print("causal_context_columns=prior_submit_count,last_known_judge_before,last_known_judge_name,prior_submit_time,time_since_prior_s")
    print("evaluation_only_columns=own_result,next_submit_result_after,time_to_next_s,pair_outcome,first_ac_submit_index,is_before_first_ac,is_first_ac,is_after_first_ac")
    print(f"output={args.out}")


if __name__ == "__main__":
    main()
