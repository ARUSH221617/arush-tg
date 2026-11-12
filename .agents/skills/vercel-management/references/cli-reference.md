# Vercel CLI Reference & Terminal Operations

This reference documents the companion terminal commands for managing Vercel projects using the official Vercel CLI (`vercel` / `vercel.cmd`).

---

## 1. CLI Execution on Windows & PowerShell

On Windows PowerShell where script execution policy may block `.ps1` wrapper scripts, always invoke the CLI using `vercel.cmd`:

```powershell
vercel.cmd --version
```

---

## 2. Authentication & Status

```powershell
# Check current logged-in account
vercel.cmd whoami

# Login interactively
vercel.cmd login

# Run commands using an explicit access token (non-interactive)
vercel.cmd list --token "$VERCEL_TOKEN"
```

---

## 3. Deployment Commands

```powershell
# List recent deployments for the linked project
vercel.cmd list

# Inspect specific deployment details
vercel.cmd inspect <deployment-url-or-id>

# Deploy current directory to preview
vercel.cmd

# Deploy current directory directly to production
vercel.cmd --prod

# Redeploy an existing deployment without rebuilding from git
vercel.cmd redeploy <deployment-url>
```

---

## 4. Log Inspection Commands

```powershell
# Stream live logs for the latest deployment
vercel.cmd logs

# View logs for a specific deployment URL or domain
vercel.cmd logs https://project-abc123-team.vercel.app

# Follow live output continuously
vercel.cmd logs -f

# Filter for errors only
vercel.cmd logs --query "status:500"
```

---

## 5. Environment Variables Commands

```powershell
# List all environment variables configured for the project
vercel.cmd env ls

# Add a new environment variable (interactive prompt for value & environment)
vercel.cmd env add VARIABLE_NAME [production|preview|development]

# Remove an environment variable
vercel.cmd env rm VARIABLE_NAME [production|preview|development]

# Pull remote environment variables into local .env.local file
vercel.cmd env pull .env.local

# Pull specifically for production environment
vercel.cmd env pull .env.production.local --environment=production
```

---

## 6. Decision Matrix: DevTools Browser MCP vs. CLI

| Scenario | Preferred Tool | Why |
| :--- | :--- | :--- |
| **Logged into Chrome browser but CLI token is missing** | **Chrome DevTools MCP** | Reuses active browser session without needing terminal tokens or logins. |
| **Interactive log filtering, visual graphs, stack traces** | **Chrome DevTools MCP** | Interactive filters (5xx, 4xx, latency, invocation drawer). |
| **Viewing encrypted secrets with UI reveal buttons** | **Chrome DevTools MCP** | Fast visual unmasking with audit trail. |
| **Pulling all environment variables into `.env.local`** | **Vercel CLI** | `vercel.cmd env pull` formats directly into valid `.env` file. |
| **Quick headless status check in automated script** | **Vercel CLI** | Instant stdout text without browser rendering overhead. |
