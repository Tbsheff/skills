# Artifact kinds

## Plan

The plan commits to a sequence. Include objective, current state, proposed approach, two to eight independently reviewable milestones, affected areas, concrete risks and mitigations, verification, rollback, non-goals, and owned open questions. A milestone describes an observable outcome, not a bucket of activity.

## Progress

The report makes change visible. Include overall status, completion, period, completed work, current work, blockers, decisions, drift from the original plan, next actions, and confidence. Say in `summary.context` what you counted to get the percentage; the schema has no field of its own for it, and `completion` renders as a headline number with a progress bar whether or not it is defensible. A blocked report must name the exact condition that prevents movement and who can clear it.

## ADR

The record preserves why. Include context, decision drivers, the selected decision, alternatives with tradeoffs and explicit rejection reasons, consequences, reversibility, migration, validation, related decisions, and supersession state. Do not disguise a proposal as an accepted decision.

## Architecture

The artifact communicates system shape. Include purpose, boundaries, components with responsibility, ownership and per-component interfaces, source locations, a scoped diagram, important flows, data ownership, invariants, failure modes, security notes, and evidence. A diagram is not a substitute for the ownership and failure tables.

## Review

Lead with the verdict. Include subject, scope, risk summary, ranked findings, exact failure conditions, evidence, recommended change, location, owner, strengths, reviewer focus, and verification. “Looks good” is not a finding. “Potential race condition” is incomplete until the triggering sequence and impact are named.

## Research

Lead with the answer and its confidence boundary. Include question, method, findings with evidence and implications, strongest counterpoints, competing interpretations, recommendations, next tests, unknowns, and sources. Do not convert absence of evidence into evidence of absence.

## Incident

Separate observation from interpretation. Include incident ID, severity, status, impact, timing, detection, chronological timeline, root cause, contributing factors, resolution, owned corrective actions, lessons, counterfactuals, and sources. Root cause names the mechanism that generated impact; it is not merely the component where symptoms appeared.

## Handoff

Optimize for resumption. Include objective, current state, completed work, constraining decisions, a compact mental model, minimum read map, known issues and workarounds, owned next steps, validation commands, boundaries, and open questions. Do not reproduce the full project history.
