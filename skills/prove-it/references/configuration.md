# Project configuration

Place configuration at `.claude/prove-it.json` or `.prove-it.json`. The Claude agent should read it before planning proof. The helper currently consumes `base` and `budgets`; the remaining fields are operational guidance for the agent.

```json
{
  "base": "origin/main",
  "budgets": {
    "max_claims": 3,
    "max_commands": 3,
    "max_screenshots": 2,
    "max_videos": 1,
    "max_video_seconds": 30
  },
  "app": {
    "start": "pnpm dev",
    "url": "http://127.0.0.1:3000",
    "ready": "http://127.0.0.1:3000/api/health"
  },
  "browser": {
    "viewport": [1440, 900],
    "record_fps": 12,
    "restore": true,
    "restore_check_text": "Dashboard"
  },
  "areas": [
    {
      "match": ["src/server/reviews/**", "src/app/**/reviews/**"],
      "route": "/admin/reviews",
      "targeted_test": "pnpm vitest run src/server/reviews"
    }
  ]
}
```

Keep commands deterministic and local. Do not put credentials in this file.

The config should eliminate rediscovery of:

- base branch
- development server command and readiness URL
- changed-domain routes
- targeted test commands
- safe test authentication/session strategy
