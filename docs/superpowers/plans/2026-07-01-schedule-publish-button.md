# Schedule tab "Publish Now" button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Publish Now" button to each assigned calendar cell in the Schedule tab, so a workout can be pushed live to the TV directly from the schedule view instead of via the Now Playing tab.

**Architecture:** Template-only change to `templates/cms.html`. The button reuses the existing `publishSession(id)` JS function and `/api/publish` endpoint verbatim — no backend or API changes.

**Tech Stack:** Flask + vanilla JS/HTML template (no build step, no frontend test framework in this repo).

## Global Constraints

- Button only appears on assigned cells (cells with a session), never on empty cells — spec: `docs/superpowers/specs/2026-07-01-schedule-publish-button-design.md`.
- Reuse `publishSession(id)` exactly as defined at `templates/cms.html:356` — no new endpoint or JS function.
- Feedback matches existing pattern: `alert("Published!")` (already inside `publishSession`), no new confirmation dialog.
- No visual "currently live" indicator on the calendar — out of scope per spec.

---

### Task 1: Add "Publish Now" button to assigned calendar cells

**Files:**
- Modify: `templates/cms.html:579-591` (the assigned-cell branch of the calendar render function)
- Test: manual verification via a running local server (this repo has no JS/DOM test framework — `tests/` only covers the Flask API)

**Interfaces:**
- Consumes: `publishSession(id)` — existing async function at `templates/cms.html:356`, takes a session id (number), POSTs to `/api/publish`, shows `alert("Published!")`. No changes to this function.
- Produces: nothing new consumed elsewhere — this is a leaf UI change.

- [ ] **Step 1: Add the button to the assigned-cell template**

Open `templates/cms.html` and find this block (around line 579):

```javascript
      cell.innerHTML = `
        <div class="cal-session-name">${esc(session.name)}</div>
        ${session.coach_notes ? `<div class="cal-coach-note">${esc(session.coach_notes)}</div>` : ""}
        <div class="cal-exercises">${exLines}</div>
        <div class="cal-cell-actions">
          <select class="cal-change-select"
                  onchange="if(this.value) calAssign('${dateStr}', parseInt(this.value))">
            <option value="">Change...</option>
            ${allSessions.map(s =>
              `<option value="${s.id}">${esc(s.name)}</option>`).join("")}
          </select>
          <button class="cal-remove-btn" onclick="calRemove('${dateStr}')">Remove</button>
        </div>`;
```

Replace it with (adds one button between the `<select>` and the "Remove" button):

```javascript
      cell.innerHTML = `
        <div class="cal-session-name">${esc(session.name)}</div>
        ${session.coach_notes ? `<div class="cal-coach-note">${esc(session.coach_notes)}</div>` : ""}
        <div class="cal-exercises">${exLines}</div>
        <div class="cal-cell-actions">
          <select class="cal-change-select"
                  onchange="if(this.value) calAssign('${dateStr}', parseInt(this.value))">
            <option value="">Change...</option>
            ${allSessions.map(s =>
              `<option value="${s.id}">${esc(s.name)}</option>`).join("")}
          </select>
          <button class="cal-publish-btn" onclick="publishSession(${session.id})">Publish Now</button>
          <button class="cal-remove-btn" onclick="calRemove('${dateStr}')">Remove</button>
        </div>`;
```

- [ ] **Step 2: Add matching CSS for the new button**

Find the existing cell-action styles (around line 120):

```css
    .cal-cell-actions { display:flex; flex-direction:column; gap:0.3rem;
```

Directly below the closing `}` of `.cal-remove-btn:hover` (around line 126), add:

```css
    .cal-publish-btn { background:#0d1f0d; border:1px solid #2a4a2a; color:#3DFF4F;
                        font-size:0.66rem; font-weight:700; text-transform:uppercase;
                        letter-spacing:0.04em; border-radius:4px; padding:0.35rem 0;
                        cursor:pointer; }
    .cal-publish-btn:hover { background:#123312; }
```

- [ ] **Step 3: Start a local server against a scratch database and verify manually**

Run:
```bash
cd ~/Projects/cs-fitness
python3 -c "
import sys, tempfile
import app as flask_app
from database import init_db
db_fd, db_path = tempfile.mkstemp()
flask_app.app.config['DATABASE'] = db_path
with flask_app.app.app_context():
    init_db()
flask_app.app.run(host='127.0.0.1', port=9091)
"
```

In another terminal, log in and create one session with a calendar entry for today so there's an assigned cell to check:
```bash
COOKIE=/tmp/cs_fitness_test_cookies.txt
curl -s -c $COOKIE -X POST http://127.0.0.1:9091/login -d "password=csfit2024" -o /dev/null
SID=$(curl -s -b $COOKIE -X POST http://127.0.0.1:9091/api/sessions -H "Content-Type: application/json" -d '{"name":"Test Workout","blocks":[]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
TODAY=$(date +%Y-%m-%d)
curl -s -b $COOKIE -X POST http://127.0.0.1:9091/api/calendar -H "Content-Type: application/json" -d "{\"date\":\"$TODAY\",\"session_id\":$SID}" -o /dev/null
```

Open `http://127.0.0.1:9091/cms` in a browser, log in with `csfit2024`, go to the Schedule tab. Confirm:
- Today's cell shows "Test Workout" with three controls: the "Change..." dropdown, a new "Publish Now" button, and "Remove".
- An empty (unassigned) cell shows only the "+ Assign session" dropdown — no "Publish Now" button.
- Clicking "Publish Now" shows the `alert("Published!")` popup.
- After dismissing the alert, open `http://127.0.0.1:9091/api/session` in a new tab and confirm it returns `{"name": "Test Workout", ...}`.

Stop the local server (Ctrl+C) once confirmed.

- [ ] **Step 4: Run the existing automated test suite to confirm no regressions**

Run: `cd ~/Projects/cs-fitness && python3 -m pytest -q`
Expected: same pass/fail count as before this change (15 passed, 2 pre-existing unrelated failures in `test_schedule.py` for the old day-of-week schedule feature — this change touches no Python code, so this count must not shift).

- [ ] **Step 5: Commit**

```bash
cd ~/Projects/cs-fitness
git add templates/cms.html
git commit -m "$(cat <<'EOF'
feat: add Publish Now button to Schedule tab calendar cells

Lets a workout be pushed live to the TV directly from the schedule
view, reusing the existing publish override mechanism.
EOF
)"
```
