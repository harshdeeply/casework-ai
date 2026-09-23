# Casework browser demo

A public, isolated walkthrough of the webhook support escalation workflow. React, TypeScript, Vite, Tailwind, and source-owned shadcn/ui-style components are in `src/components/ui`. The app imports the same synthetic incident and runbook fixtures as the Python reference implementation.

```bash
npm ci
npm test
npm run lint
npm run build
npm run dev
```

Choose ticket **T-1042**. The scheduled retry has no later log record. Add the sample HTTP 200, observe the stale evidence warning, refresh the snapshot, approve the revised draft, and hand it to the demo desk. You can also create an isolated ticket and add valid delivery attempts.

The demo has no authentication and stores all changes in each browser's `localStorage`. Its handoff is simulated inside that same browser. Never enter real customer records here. The Python + SQLite service at the repository root is independently testable and is not exposed by this deployment.

The shadcn CLI registry could not be reached in the initial development environment; the Button, Badge, Card, Input, and Textarea source components and `components.json` were created directly following its source-owned component pattern.
