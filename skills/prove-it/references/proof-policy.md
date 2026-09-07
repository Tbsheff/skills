# Proof policy

## Goal

Produce the smallest evidence set that lets a reviewer distinguish “implemented” from “observed working.” Proof is not a second CI system and not a full regression suite.

## Fast path budget

| Resource | Budget |
|---|---:|
| Claims | 3 |
| Targeted backend commands/requests | 3 |
| Browser flows | 1 |
| Screenshots | 2 |
| Videos | 1 |
| Video duration | 30 seconds |

Choose expanded mode only when the risk is real. Expanded mode is not permission to collect indiscriminately.

## Evidence ladder

Prefer evidence in this order:

1. Existing focused assertion/test.
2. Direct local API or command assertion.
3. Before/action/after database or state assertion.
4. Final-state screenshot.
5. Short deterministic browser interaction video.
6. HAR for a network-contract claim.
7. Trace/profile for a timing or debugging claim.

Do not climb the ladder after the claim is already established.

## Claim compression

Combine redundant claims. For example:

- “Save sends a request.”
- “Request returns 200.”
- “Saved value appears after reload.”

Usually compress to:

> “Saving the reviewer persists it and it remains visible after reload.”

Use direct backend evidence plus one UI replay if both persistence and visibility matter.

## Escalation triggers

Consider expanded proof for:

- authorization or tenant boundaries
- payment or billing behavior
- destructive operations
- schema/data migrations
- asynchronous jobs with durable side effects
- security-sensitive input handling
- a bug that was intermittent or expensive
- a diff touching several independently observable workflows

Even in expanded mode, rank claims and prove must-claims first.

## Failure policy

Fail fast in increasing-cost order. If a targeted test or direct API assertion fails, do not spend time producing a polished browser video. Fix the issue or report the failed claim.

Do not discard failed evidence merely to make a green report. A later successful attempt may replace stale media, but the manifest should retain a note explaining the rerun.
