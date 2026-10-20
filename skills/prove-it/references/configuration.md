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
  ],
  "classify": {
    "apps/*/lib/core/**": "backend"
  },
  "ignore_dirty": ["packages/*/package.json", "dist/**"]
}
```

`classify` maps a path glob to a kind, or to a list of kinds, when the built-in scan gets a path wrong. The first glob that matches wins. The kinds are `frontend`, `backend`, `database`, `library`, `security`, `docs`, `config`, `tests`, and `other`. Without a rule, a `public/` or `static/` folder is `frontend` only for static files (images, fonts, HTML, CSS) or when it is an asset root such as `public/` or `apps/web/public/`. A code file in a deeper `public/` folder, such as `lib/core/orders/public/`, is `backend`.

`ignore_dirty` lists path globs for generated files. `init --pr` and `publish` do not count these files when they check for a clean tree. When the tree is dirty, the error names each dirty file.

Store instructions, not generated evidence. Do not put credentials or tokens in this file.

A per-run scenario ([scenario.md](scenario.md)) reads `app.start`, `app.ready`, `browser.viewport`, and the matched area's `route` and `targeted_test` when it does not set them. For media, `app.start` must contain `{port}`, because base and change run at the same time. Keep shared values here. Put run-only values in the scenario.
