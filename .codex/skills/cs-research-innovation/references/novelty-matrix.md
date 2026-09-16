# Novelty strength matrix

Use this reference when ranking research directions or testing whether a thesis contribution is technically and empirically strong enough.

| Axis | Weak variation | Stronger research contribution | Decisive evidence |
|---|---|---|---|
| Representation | add more event counts | represent latent programming state, duration, or semantic progress | state ablation and cross-user/task transfer |
| Inference | replace rules with RF or an LLM | model uncertainty, temporal dependency, and missing observations | calibration, abstention, state-level error analysis |
| Decision | tune an idle threshold | optimize timing and intensity under interruption risk | randomized benefit-disruption frontier |
| Feedback | observe whether input resumes | estimate the counterfactual effect of showing assistance | candidate-level randomized holdout |
| Navigator | generate a suggestion | implement and evaluate observation, questioning, navigation, or pacing functions | matched human-Navigator comparison |
| Personalization | set a threshold for each user | learn safely from acceptance, rejection, and cold-start context | temporal and new-user evaluation |
| Learning | report immediate AC | evaluate retention, transfer, help-seeking, and dependence | delayed transfer or longitudinal study |
| System | wrap a model in a UI | meet measurable latency, privacy, auditability, and control constraints | deployment measurements and failure audit |

## Contribution test

A strong direction normally contains all four:

1. a precise limitation in prior work;
2. a mechanism or representation that addresses it;
3. a baseline and ablation capable of disproving the mechanism;
4. evidence at the same level as the claim.

If one is missing, narrow the claim or redesign the study.

## Claim boundaries

- Classifier performance supports recognition, not usefulness.
- Shadow-mode performance supports feasibility, not causal benefit.
- Randomized prompt effects support short-term intervention impact, not learning gain.
- Transfer or longitudinal evidence is needed for educational improvement claims.
- Human comparison should compare specific Navigator functions under matched conditions, not only average completion time.
