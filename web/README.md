# Casework browser demo

**[Open the live workbench](https://casework-demo.netlify.app/)**

A public, isolated walkthrough of the webhook support escalation workflow. React, TypeScript, Vite, Tailwind, and source-owned shadcn/ui-style components are in `src/components/ui`. The app imports the same synthetic incident and runbook fixtures as the Python reference implementation.

```bash
npm ci
npm test
npm run lint
npm run build
npm run dev
```

Choose ticket **T-1042**. Its source-declared export ends before the scheduled retry, so the initial draft cannot confirm whether the retry occurred. Advance export coverage without adding an attempt: the old snapshot becomes stale. Refresh, then add the sample HTTP 200 and refresh again. Approve the revised draft and hand it to the demo desk. You can also create a fictional ticket and add valid delivery attempts.

The demo has no authentication and stores all changes in each browser's `localStorage`. Its handoff is simulated inside that same browser. Never enter real customer records here. The Python + SQLite service at the repository root is independently testable and is not exposed by this deployment.

The operator profile is fictional. The logout button only explains that there is no account session. The monochrome UI does not imply production identity or integration.

The shadcn CLI registry could not be reached in the initial development environment; the Button, Badge, Card, Input, and Textarea source components and `components.json` were created directly following its source-owned component pattern.

## Hosting

The live Netlify project is deployed from the production `dist/` build and configured with the root [`netlify.toml`](../netlify.toml). The current site was uploaded as a manual deployment; pushing to GitHub does not automatically update the live site. To update it, run `npm ci && npm run build` in `web/` and upload the contents of `web/dist/` to the existing Netlify project. The `public/_headers` file is copied into the build and sets response security headers.
