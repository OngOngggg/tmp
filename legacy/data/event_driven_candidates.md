# Event-driven causal candidates

- sessions=100
- candidates=462
- types={'idle_30s': 448, 'backspace_pause_2s': 14}
- causal features use only events before trigger_time.
- outcome_* columns are post-trigger analysis fields and must not be used by an online trigger.
- one idle gap produces one idle_30s candidate; 60/120 second extensions are not duplicate trigger rows.
