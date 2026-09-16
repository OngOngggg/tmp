---
name: cs-research-innovation
description: Discover and evaluate technically deep computer-science research directions for behavior modeling, human-AI interaction, programming systems, educational technology, and intelligent developer tools. Use for research gaps, novelty assessment, thesis framing, and decisive experiment design; do not use for ordinary implementation or prose polishing.
metadata:
  short-description: Computer-science research novelty and thesis design
---

# Computer-science research innovation

Develop technically substantive and empirically falsifiable research rather than decorating an existing prototype with a more complex model.

## Frame the problem

State the analysis unit, decision time, observable history, unknown state, action or intervention, and outcome horizon. Classify every field as available before the decision, observed afterward, or unavailable.

For interactive behavioral systems, keep these distinctions explicit:

- state estimation versus outcome prediction;
- need for assistance versus readiness to be interrupted;
- natural recovery versus an intervention effect;
- proxy labels versus directly observed ground truth.

## Map prior work and gaps

Search and compare work along separate axes: target application, technical mechanism, interaction paradigm, and evaluation or causal identification.

For each relevant paper, extract its task, prediction unit, data, labels, model, split, metrics, intervention, and limitations. Do not present a paper as a direct baseline when its prediction unit, information boundary, or outcome differs materially.

Distinguish missing capability, missing mechanism, missing evidence, missing setting, and missing constraint. The last category includes latency, privacy, uncertainty, interruption cost, and human control.

## Generate and filter directions

Generate alternatives from at least three different axes: representation, inference, decision, system, or evaluation. For each direction provide the exact research question, prior-work gap, proposed mechanism, minimum technical artifact, decisive experiment and baseline, likely failure mode, and falsification or stopping criterion.

Downgrade a direction if its main novelty is only changing a threshold, swapping the classifier, adding an LLM as a second judge, adding features without a representation hypothesis, reporting correlated-window F1, using future behavior online, claiming intervention benefit from observational recovery, comparing only with a weak baseline, or omitting mechanism ablations and cross-user/task/temporal tests.

Read [references/novelty-matrix.md](references/novelty-matrix.md) when comparing candidate innovation points or judging whether a thesis is deep enough.

## Design evidence before implementation

Build a claim-evidence matrix with one row per claim:

| Claim | Required comparison | Unit | Primary measure | Main threat |
|---|---|---|---|---|
| a state can be recognized | independent labels and simple baselines | user/session split | macro F1, PR-AUC, calibration | label circularity |
| a policy reduces interruption | no-prompt or delayed control | candidate/session | disruption and prompts/session | selection bias |
| an intervention helps | randomized holdout | user/task | time-to-recovery and task outcome | natural recovery |
| AI performs a Navigator function | matched human condition | task/user | timing, quality, control, transfer | unfair comparison |

Use group-aware splits. Report uncertainty intervals, class imbalance, abstention, false prompts per session, latency, cost, and calibration when they affect the claim.

## Choose technical depth for a reason

For programming-behavior and AI Navigator research, consider these lenses only when they resolve a named limitation:

- HMM, HSMM, temporal point processes, or state-space models for partially observed state and duration;
- survival or competing-risks models for next edit, run, submit, recovery, or departure;
- multimodal fusion of event streams, code diffs or AST changes, and judge context;
- selective prediction, calibration, and uncertainty-aware abstention;
- causal inference and randomized intervention evaluation;
- constrained contextual bandits or POMDPs for timing and assistance intensity;
- mixed-initiative interaction and interruption management;
- functional decomposition of Driver and Navigator work.

Do not add a method merely to make the stack appear deeper. Explain what hypothesis the method represents and what ablation could refute it.

## Stage the thesis

Separate the evidence levels:

1. Offline foundation: causal windows, reproducible labels, group-aware baselines, and error analysis.
2. Shadow deployment: real candidate distribution, missing context, latency, and operational cost.
3. Randomized online evaluation: prompt versus holdout, user responses, and short-term effects.
4. Human comparison: AI Navigator versus human Navigator or conventional pair programming.
5. Longitudinal or transfer evaluation: retention, dependence, trust, and generalization.

Offline agreement supports recognition, not intervention benefit. Short-term recovery supports an immediate behavioral effect, not learning transfer.

## Project-specific invariants

- Keep `Need`, `Interruptibility`, and `Outcome` separate.
- Treat `previous_submission_result` as a proxy unless result-visible time is verified.
- Exclude `outcome_*`, next-submit, and pair-level long-term fields from online trigger features.
- Preserve `uncertain` for ambiguous thinking, checking, waiting, and away periods.
- Inspect non-triggered windows to estimate candidate-recall blind spots.
- Report candidate rate, suppression rate, prompts/session, false prompts/session, latency, cost, and group-aware metrics.
- Describe AI as implementing a subset of Navigator functions unless controlled evidence supports a stronger claim.
- Keep raw student code and behavior data out of public repositories.

When relevant, consult `DISSERTATION_ROADMAP.md`, `LABEL_SPEC.md`, `PROJECT_HANDBOOK.md`, and `resources/papers/literature_evidence_for_report.md`.

## Research-advice output

Present the recommended direction first, followed by alternatives, novelty mechanism, research questions and hypotheses, minimum implementation, decisive experiments, hard risks, falsification criteria, and staged next actions.

If current literature access is unavailable, say so and distinguish verified evidence from hypotheses. Never invent citations, datasets, or reported results.
