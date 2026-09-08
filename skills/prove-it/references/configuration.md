# Project configuration

Use `.claude/prove-it.json` or `.prove-it.json` when the repo needs a specific base, app startup, route, test command, or safe auth recipe.

```json
{
  "base": "origin/main",
  "budgets": {
    "max_claims": 3,
    "max_commands": 3,
    "max_screenshots": 2,
    "max_videos": 1,
    "max_diagrams": 1,
    "max_video_seconds": 30
  },
  "app": {
    "start": "pnpm dev",
    "url": "http://127.0.0.1:3000",
    "ready": "http://127.0.0.1:3000/api/health"
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

Store instructions, not generated evidence. Do not put credentials or tokens in this file.
