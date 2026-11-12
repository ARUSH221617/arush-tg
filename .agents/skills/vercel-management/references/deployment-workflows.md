# Vercel Deployment Workflows

This guide explains how to inspect, troubleshoot, promote, and roll back deployments using Chrome DevTools MCP.

---

## 1. Accessing Deployments

Direct URL:
```text
https://vercel.com/<team>/<project>/deployments
```

### Steps to Inspect Recent Deployments:
1. `navigate_page(pageId: <id>, url: "https://vercel.com/<team>/<project>/deployments")`
2. `wait_for(pageId: <id>)`
3. `take_snapshot(pageId: <id>)`
4. The snapshot lists deployment entries. Each entry includes:
   - **Status**: `Ready` (deployed), `Building` (active), `Error` (failed), `Queued`, `Canceled`.
   - **Target**: Production (branch `main`/`master`) vs Preview (feature branches or PRs).
   - **Commit**: Commit message, commit SHA hash, and author.
   - **URL**: Automatic preview URL (e.g. `https://project-git-branch-team.vercel.app`).
   - **Age / Created**: When the build was triggered.

---

## 2. Diagnosing Build Errors

When a deployment shows `Error` or fails to build:
1. In the snapshot of `/deployments`, locate the failing deployment link and call `click(pageId: <id>, uid: "<deployment-link-uid>")`.
2. The page navigates to `https://vercel.com/<team>/<project>/<deployment-id>`.
3. In the deployment detail view, find the **Building** or **Build Logs** section.
4. Take a snapshot or call `evaluate_script`:
   ```javascript
   () => {
     const logEl = document.querySelector('pre') || document.querySelector('[class*="terminal"]');
     return logEl ? logEl.innerText : document.body.innerText;
   }
   ```
5. Scan for standard build failures:
   - **Missing Environment Variable**: Look for errors like `Missing NEXT_PUBLIC_...`, `DATABASE_URL is not set`, or validation errors (`zod`, `envalid`).
   - **TypeScript / Linter Errors**: Look for `Type error: Property ... does not exist`, `ESLint error`.
   - **Dependency Errors**: `npm ERR! 404`, `Cannot find module`, or lockfile mismatch.
   - **Route / SSG Failures**: `Error occurred prerendering page "/api/..."` or dynamic server usage during static export.

---

## 3. Promoting a Preview Deployment to Production

If a preview deployment has been verified and needs to go live:
1. Open the deployment detail page (`https://vercel.com/<team>/<project>/<deployment-id>`).
2. Locate the **Promote to Production** button or the three-dots action menu (`...`) in the header.
3. Call `click(pageId: <id>, uid: "<promote-button-uid>")`.
4. A confirmation dialog appears. Call `take_snapshot` to locate the confirm button.
5. Call `click` on "Promote" / "Confirm".

---

## 4. Performing an Instant Rollback

If the current production deployment introduced a critical bug:
1. Navigate to `/deployments`.
2. Find the last known working deployment with status `Ready`.
3. Click the three-dots menu button `...` on that deployment row.
4. Select **Rollback to this deployment** or **Instant Rollback**.
5. Confirm in the modal. Vercel will immediately redirect production traffic to that deployment hash without needing a rebuild.
