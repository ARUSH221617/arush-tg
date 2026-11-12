# Vercel Environment Variables Management

This guide details how to read, inspect, create, edit, and delete environment variables on Vercel using Chrome DevTools MCP.

---

## 1. Accessing Environment Variables

Direct URL:
```text
https://vercel.com/<team>/<project>/settings/environment-variables
```

---

## 2. Reading Existing Environment Variables

1. `navigate_page(pageId: <id>, url: "https://vercel.com/<team>/<project>/settings/environment-variables")`
2. `wait_for(pageId: <id>)`
3. `take_snapshot(pageId: <id>)`
4. The table displays:
   - **Key Name**: e.g., `DATABASE_URL`, `NEXT_PUBLIC_API_URL`, `JWT_SECRET`.
   - **Value**: Masked as bullets (`••••••••`) for sensitive values or plain text.
   - **Environments**: `Production`, `Preview`, and/or `Development`.
   - **Updated**: Timestamp of last edit.

### Revealing Masked Secret Values
To read the secret value:
1. Locate the variable row in the snapshot.
2. Find the eye icon or "Show / Reveal" button associated with that key.
3. Call `click(pageId: <id>, uid: "<eye-button-uid>")`.
4. Call `take_snapshot(pageId: <id>)` or call `evaluate_script` to read the revealed text string.
5. If Vercel prompts for 2FA / Password confirmation to reveal sensitive values, inform the user immediately.

---

## 3. Adding a New Environment Variable

At the top of the Environment Variables page is the **Create New Variable** form:

### Workflow:
1. `take_snapshot(pageId: <id>)` to identify the input fields:
   - **Key Input**: Placeholder `NAME` or `EXAMPLE_NAME`.
   - **Value Input**: Text input or multiline textarea placeholder `VALUE`.
   - **Environment Checkboxes**: Checkboxes labeled `Production`, `Preview`, and `Development`.
2. Enter the Key name:
   `fill(pageId: <id>, uid: "<key-input-uid>", value: "MY_VARIABLE_NAME")`
3. Enter the Value:
   `fill(pageId: <id>, uid: "<value-input-uid>", value: "my-secret-value-123")`
4. Configure Environments:
   - Check or uncheck target environments as required:
     - `fill(pageId: <id>, uid: "<prod-checkbox-uid>", value: "true")`
     - `fill(pageId: <id>, uid: "<preview-checkbox-uid>", value: "true")`
     - `fill(pageId: <id>, uid: "<dev-checkbox-uid>", value: "true")`
5. Click **Save**:
   - Locate the `Save` button (`Save` or `Add`).
   - Call `click(pageId: <id>, uid: "<save-button-uid>")`.
6. Verification:
   - Wait 1 second, then call `take_snapshot(pageId: <id>)`.
   - Confirm a success toast appears and the new variable is listed in the table.

---

## 4. Editing an Existing Environment Variable

1. Locate the target variable row in the table snapshot.
2. Find the action menu button on the right side of the row (three dots `...` or `Edit`).
3. Call `click(pageId: <id>, uid: "<action-menu-uid>")`.
4. From the dropdown menu, call `click` on **Edit**.
5. An edit modal or inline editable inputs will open.
6. Take snapshot, update the value using `fill`, adjust target environments if needed.
7. Click **Save**.
8. Verify the updated value in the table.

> [!IMPORTANT]
> **Redeployment Requirement**: Changes made to environment variables do **NOT** take effect on already-running deployments. You must trigger a new deployment or redeploy the current production deployment for the new environment variable values to become active in production.

---

## 5. Deleting an Environment Variable

> [!CAUTION]
> Deleting an environment variable in Production can cause runtime outages or crash running serverless functions. Always verify with the user before executing a delete.

1. Locate the target variable row in the table snapshot.
2. Click the three-dots menu button `...` for that row.
3. Click **Delete** or **Remove**.
4. A confirmation modal will appear ("Are you sure you want to delete...?").
5. Take snapshot, find the confirm delete button (often styled in red / destructive), and call `click`.
6. Verify removal from the table.
