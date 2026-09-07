# Artifact contract

`manifest.json` is the canonical transient record. `proof.md` and `report.html` are projections used only while preparing the PR update.

## Run and PR target

```json
{
  "schema_version": 1,
  "tool": { "name": "prove-it", "version": "1.1.0" },
  "run": {
    "id": "prove-it-pr-123-abc12345-xyz",
    "title": "Persist review assignment",
    "created_at": "2026-09-04T18:00:00Z",
    "repo_root": "/repo",
    "artifact_dir": "/tmp/prove-it-pr-123-abc12345-xyz",
    "ephemeral": true,
    "mode": "fast"
  },
  "target_pr": {
    "number": 123,
    "url": "https://github.com/owner/repo/pull/123",
    "repo": "owner/repo",
    "baseRefName": "main",
    "headRefName": "feature/reviewer",
    "headRefOid": "abc12345..."
  }
}
```

A human-invoked PR run is valid only while the PR and local checkout still point at `headRefOid`.

## Claim

```json
{
  "id": "C1",
  "text": "Saving a review persists the selected reviewer.",
  "expected": "A fresh read returns the selected reviewer id.",
  "method": "test",
  "priority": "must",
  "status": "passed",
  "observed": "A fresh read returned reviewer-test.",
  "evidence": []
}
```

Statuses: `pending`, `passed`, `failed`, `not_proven`, `skipped`.

## Evidence

Every evidence entry includes:

- stable type and human label
- evidence-local pass/fail result
- path relative to the temporary proof directory
- SHA-256 and byte size
- captured observation
- type-specific metadata such as command, exit code, HTTP status, image dimensions, or video duration

Evidence types:

```text
command test http database log file
screenshot video console errors har trace
```

Imported evidence is copied into transient `backend/` or `frontend/` directories and validated so paths cannot escape the run directory.

## Projection rules

- The PR table shows claims and compact evidence, not raw logs.
- The first screenshot is the featured key state.
- The first video is the featured interaction.
- Command and HTTP details are summarized in collapsible sections.
- Images and videos are uploaded with `gh pr edit --attach`.
- Text logs are summarized into the PR and then deleted locally with the rest of the temp run.

## Lifetime

The manifest and evidence directory are not a permanent cache. A successful publish deletes them. The durable representation is the PR body and GitHub-hosted media.
