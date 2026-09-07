# PR targeting

Prove It is bound to an existing pull request and its exact head SHA.

## Resolve the target

Human invocation with no argument:

```text
/prove-it
```

uses the PR for the current branch (`gh pr view`).

An explicit argument may be a PR number or URL:

```text
/prove-it 123
/prove-it https://github.com/owner/repo/pull/123
```

The helper stores:

- PR number
- PR URL
- repository name
- title/body
- base branch
- head branch
- head object ID

## Local checkout requirements

The normal fast path requires:

```text
local HEAD == GitHub PR head SHA
working tree == clean
```

Do not silently prove a stale local checkout. Do not automatically check out another branch or mutate the user's worktree just to run proof. If the PR head does not match, report the mismatch and have the human update/check out the PR before rerunning.

## Why strict SHA binding matters

Screenshots and runtime commands are otherwise easy to detach from the code a reviewer sees. Binding both init and publish to the same PR head prevents a proof captured for revision A from being attached after revision B is pushed.
