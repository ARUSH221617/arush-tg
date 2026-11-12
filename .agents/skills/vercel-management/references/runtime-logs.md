# Vercel Runtime & Function Logs

This guide explains how to stream, filter, search, and inspect runtime logs for serverless functions, edge middleware, and static requests on Vercel using Chrome DevTools MCP.

---

## 1. Accessing Runtime Logs

Direct URL:
```text
https://vercel.com/<team>/<project>/logs
```

### Steps to Open Runtime Logs:
1. `navigate_page(pageId: <id>, url: "https://vercel.com/<team>/<project>/logs")`
2. `wait_for(pageId: <id>)`
3. `take_snapshot(pageId: <id>)`

---

## 2. Managing the Live Stream

Vercel runtime logs stream in real-time. Continuous streaming can cause DOM element UIDs to shift while you are trying to click or inspect them.

### Best Practice: Pause Before Inspecting
1. In the top bar of the log viewer, locate the **Live** indicator / toggle button.
2. If new logs are flowing rapidly, click the **Pause** button (`uid` from snapshot).
3. Once paused, take a fresh snapshot. The snapshot element UIDs will remain stable.

---

## 3. Filtering and Searching Logs

Vercel provides interactive filter controls on the `/logs` page:

| Filter Type | How to Apply via DevTools | Value Examples |
| :--- | :--- | :--- |
| **Status Filter** | Click the Status dropdown / pill | `5xx (Errors)`, `4xx (Warnings)`, `2xx (Success)` |
| **Environment Filter** | Click Environment selector | `Production`, `Preview`, `Branch: staging` |
| **Search Query** | Fill the search input (`input[placeholder*="Search"]`) | `TypeError`, `auth`, `request_id`, `api/v1/user` |
| **Time Range** | Click time dropdown | `Past 15 minutes`, `Past 1 hour`, `Past 24 hours` |

### Step-by-Step Search Workflow:
1. `take_snapshot(pageId: <id>)`
2. Locate the search input (e.g. `Search logs or enter a query...`).
3. Call `fill(pageId: <id>, uid: "<search-input-uid>", value: "status:500")` or `value: "error"`
4. Call `press_key(pageId: <id>, key: "Enter")`
5. Wait 1-2 seconds for query results to render, then call `take_snapshot(pageId: <id>)` to view matching events.

---

## 4. Inspecting Individual Log Details (Drawer / Inspector)

To inspect detailed request payloads, response times, memory usage, and stack traces:
1. In the snapshot of log rows, find the row of interest (e.g., a row marked with red dot or `500 POST /api/...`).
2. Click the row: `click(pageId: <id>, uid: "<log-row-uid>")`.
3. A detail drawer slides open from the right side.
4. Call `take_snapshot(pageId: <id>)` to read:
   - **Invocation Details**: Duration (e.g. `142ms`), Memory Used (e.g. `85 MB / 1024 MB`), Region (`iad1`).
   - **Request**: HTTP Method, URL Path, Query Params, Request Headers (`x-vercel-id`, User-Agent).
   - **Response**: Status Code, Cache status (`HIT`, `MISS`, `BYPASS`).
   - **Console Output / Stack Trace**: The exact multiline error log and Node.js / Python stack trace.

---

## 5. Extracting Logs Programmatically

If the log viewer contains many lines, extracting them via `evaluate_script` is faster and cleaner than reading a long snapshot:

```javascript
() => {
  const lines = Array.from(document.querySelectorAll('[data-testid="log-row"], [class*="log-row"]'))
    .map(el => el.innerText.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  
  return lines.length > 0 ? lines.slice(-30) : ["No log rows found"];
}
```
Call `evaluate_script(pageId: <id>, function: "<above-script>")` to receive clean array output.
