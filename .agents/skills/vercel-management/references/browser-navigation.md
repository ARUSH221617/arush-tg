# Vercel Browser Navigation with Chrome DevTools MCP

This guide details how to navigate and interact with Vercel web console (`vercel.com`) using Chrome DevTools MCP tools (`chrome-devtools-mcp`).

---

## 1. Tool Call Lifecycle & Rules

Always execute browser interactions following this sequence:
1. **Locate or Open Page**:
   - Call `list_pages` to see if a Vercel tab is already open.
   - If a Vercel tab is found, use its `pageId`.
   - If not, call `new_page(url: "https://vercel.com/...")` to create one and obtain `pageId`.
2. **Wait for Hydration**:
   - Call `wait_for(pageId: <id>)` (e.g., waiting for selector `main`, `table`, or `input`) or allow short settling to ensure Next.js client hydration finishes.
3. **Capture Snapshot**:
   - Call `take_snapshot(pageId: <id>)`. This returns an accessibility tree with element `uid`s (e.g. `1_12`).
   - *Never guess or hardcode element UIDs*. Always get the latest snapshot before clicking or typing.
4. **Interact**:
   - Click: `click(pageId: <id>, uid: "<uid>")`
   - Fill/Type: `fill(pageId: <id>, uid: "<uid>", value: "...")`
   - Keypress: `press_key(pageId: <id>, key: "Enter")`
   - For complex DOM data extraction: `evaluate_script(pageId: <id>, function: "() => ...")`

---

## 2. Vercel URL Anatomy

Vercel URLs follow a predictable structure:

| Purpose | URL Format | Notes |
| :--- | :--- | :--- |
| **Dashboard Root** | `https://vercel.com/dashboard` | Shows all projects, teams, and recent events |
| **Project Overview** | `https://vercel.com/<team-or-username>/<project-name>` | Production domain, latest deployment card |
| **Deployments List** | `https://vercel.com/<team-or-username>/<project-name>/deployments` | Chronological list of deployments & filters |
| **Deployment Detail** | `https://vercel.com/<team-or-username>/<project-name>/<deployment-id-or-url>` | Build logs, domains, functions, inspection |
| **Runtime Logs** | `https://vercel.com/<team-or-username>/<project-name>/logs` | Real-time & historic serverless/edge logs |
| **Environment Variables** | `https://vercel.com/<team-or-username>/<project-name>/settings/environment-variables` | Key-value pairs across Prod/Preview/Dev |
| **General Settings** | `https://vercel.com/<team-or-username>/<project-name>/settings` | Build command, output dir, root dir, Git link |
| **Domains** | `https://vercel.com/<team-or-username>/<project-name>/settings/domains` | Custom DNS, SSL certs, redirects |

---

## 3. Session & Authentication Handling

Chrome DevTools runs with the user's persistent Chrome profile. If the user is logged into Vercel in Chrome, the session is already active.

### Detecting Authentication Status
1. Navigate to `https://vercel.com/dashboard`.
2. Call `take_snapshot(pageId: <id>)`.
3. Check the page title and URL:
   - **Authenticated**: Shows "Dashboard", projects list, team selector, or avatar.
   - **Unauthenticated**: Redirected to `https://vercel.com/login`.

### If Unauthenticated:
- Alert the user: "You are not logged into Vercel in your Chrome profile. Please log in at https://vercel.com/login (or via GitHub/GitLab SSO)."
- Once the user logs in, call `take_snapshot` again to confirm access and proceed.

---

## 4. Discovering Team and Project Names

If the user does not specify their Vercel team or project name:
1. **Check local git**:
   - Check `.git/config` for the repository name (e.g. `arush-tg`).
   - Check `package.json` for `"name"`.
2. **Search in Vercel Dashboard**:
   - Navigate to `https://vercel.com/dashboard`.
   - Take snapshot to see the search bar (`Search projects...`).
   - Use `fill` to type the project name, or inspect the project cards listed on the dashboard.
   - Extract the full URL path: `https://vercel.com/<team-slug>/<project-slug>`.
