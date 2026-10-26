# Quick Entry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Quick Entry" tab to the CS Fitness CMS that lets the coach transcribe multiple sessions from TrainHeroic in one sitting using a spreadsheet-style keyboard-driven interface.

**Architecture:** Pure frontend addition to `templates/cms.html`. Three DOM row types (session, block, exercise) nested inside a scrollable panel. State lives in the DOM; at save time the tree is walked to build API payloads. Reuses the existing `POST /api/sessions` endpoint — no backend changes.

**Tech Stack:** Vanilla JS, HTML, CSS. Flask Jinja2 template. Existing pytest suite for backend smoke checks.

## Global Constraints

- All styling must use existing CSS custom properties and class conventions from `templates/cms.html` (`.btn`, `.btn-green`, `.btn-dark`, `.btn-red`, `input`, `select`)
- No new dependencies
- Password: `csfit2024` (for manual testing)
- Server: `python3 app.py` from `/Users/ewantaylormacbookair/Projects/cs-fitness`
- Tests: `pytest tests/ -v` from project root

---

### Task 1: Tab button + empty panel + CSS

**Files:**
- Modify: `templates/cms.html`

**Interfaces:**
- Produces: `panel-quickentry` div (used by Tasks 2–5), `switchTab('quickentry')` already works via existing tab machinery

- [ ] **Step 1: Add the tab button**

In `templates/cms.html`, find the tabs bar:
```html
<div class="tabs">
  <div class="tab active" data-tab="library">Library</div>
  <div class="tab" data-tab="editor">Editor</div>
  <div class="tab" data-tab="schedule">Schedule</div>
  <div class="tab" data-tab="nowplaying">Now Playing</div>
</div>
```
Add the Quick Entry tab as the fifth item:
```html
<div class="tabs">
  <div class="tab active" data-tab="library">Library</div>
  <div class="tab" data-tab="editor">Editor</div>
  <div class="tab" data-tab="schedule">Schedule</div>
  <div class="tab" data-tab="nowplaying">Now Playing</div>
  <div class="tab" data-tab="quickentry">Quick Entry</div>
</div>
```

- [ ] **Step 2: Add the empty panel**

After the `<!-- ── NOW PLAYING ── -->` panel's closing `</div>`, add:
```html
<!-- ── QUICK ENTRY ── -->
<div class="panel" id="panel-quickentry">
  <div class="qe-toolbar">
    <button class="btn btn-dark" onclick="addQESession()">+ Add Session</button>
    <button class="btn btn-green" id="qe-save-btn" onclick="saveAllQESessions()">Save All</button>
  </div>
  <div id="qe-container"></div>
  <div class="qe-footer">
    <button class="btn btn-dark" onclick="addQESession()">+ Add Session</button>
  </div>
</div>
```

- [ ] **Step 3: Add CSS**

Inside the `<style>` block, before the closing `</style>`, add:
```css
/* ── QUICK ENTRY ── */
.qe-toolbar { display:flex; justify-content:space-between; align-items:center;
              margin-bottom:1rem; }
.qe-footer  { margin-top:0.8rem; }

.qe-session { margin-bottom:1.2rem; }

.qe-session-row { display:grid;
  grid-template-columns:5rem 1fr 8rem 1fr 2rem;
  gap:0.4rem; align-items:center;
  background:#0a0a0a; border-top:2px solid #2a2a2a;
  padding:0.5rem 0.6rem; }
.qe-session-label { color:#3DFF4F; font-size:0.7rem; font-weight:800;
                    text-transform:uppercase; letter-spacing:0.08em; }

.qe-block { margin-left:1.5rem; }
.qe-block-row { display:grid;
  grid-template-columns:5rem 1fr 2rem;
  gap:0.4rem; align-items:center;
  background:#0d0d0d; border-top:1px solid #1a1a1a;
  padding:0.4rem 0.6rem; }
.qe-block-label { color:#666; font-size:0.7rem; font-weight:700;
                  text-transform:uppercase; letter-spacing:0.06em; }

.qe-exercise { display:grid;
  grid-template-columns:3.5rem 1fr 6rem 2rem;
  gap:0.4rem; align-items:center;
  margin-left:3rem; padding:0.3rem 0.6rem; }
.qe-exercise.cardio { grid-template-columns:1fr 6rem 2rem; }

.qe-add-ex { display:block; margin-left:3rem; margin-top:0.2rem;
             background:none; border:1px dashed #1a3a1a; border-radius:4px;
             color:#3DFF4F55; font-size:0.72rem; padding:0.25rem 0.6rem;
             cursor:pointer; text-align:left; }
.qe-add-ex:hover { color:#3DFF4F; border-color:#3DFF4F44; }
.qe-add-block { display:block; margin-left:1.5rem; margin-top:0.3rem;
                background:none; border:1px dashed #222; border-radius:4px;
                color:#444; font-size:0.75rem; padding:0.3rem 0.6rem;
                cursor:pointer; text-align:left; }
.qe-add-block:hover { color:#3DFF4F; border-color:#3DFF4F44; }
.qe-remove { padding:0.2rem 0.45rem; font-size:0.8rem; line-height:1; }
```

- [ ] **Step 4: Verify tab appears**

Start server: `cd /Users/ewantaylormacbookair/Projects/cs-fitness && python3 app.py`
Open `http://localhost:9090`, log in (password: `csfit2024`).
Expected: "Quick Entry" tab visible in the nav bar. Clicking it shows an empty panel with "+ Add Session" and "Save All" buttons.

- [ ] **Step 5: Commit**
```bash
git add templates/cms.html
git commit -m "feat: add Quick Entry tab scaffold with CSS"
```

---

### Task 2: Add / remove session rows

**Files:**
- Modify: `templates/cms.html` (JS section)

**Interfaces:**
- Produces: `addQESession()` — appends a `.qe-session` div to `#qe-container`; called by Task 3's `addQEBlock()`
- Produces: `.qe-session` DOM structure (consumed by Tasks 3, 4, 5)

- [ ] **Step 1: Add `addQESession` to the script**

Inside the `<script>` block, before the final `loadSessions();` line, add:

```js
// ── Quick Entry ───────────────────────────────────────────
function addQESession() {
  const container = document.getElementById('qe-container');
  const div = document.createElement('div');
  div.className = 'qe-session';
  div.innerHTML = `
    <div class="qe-session-row">
      <span class="qe-session-label">Session</span>
      <input type="text" class="qe-session-name" placeholder="e.g. Monday S&amp;C" />
      <select class="qe-session-format">
        <option value="strength">Strength</option>
        <option value="cardio">Cardio / Class</option>
      </select>
      <input type="text" class="qe-session-notes" placeholder="Coach notes..." />
      <button class="btn btn-red qe-remove"
              onclick="this.closest('.qe-session').remove()">×</button>
    </div>
    <div class="qe-blocks"></div>
    <button class="qe-add-block" onclick="addQEBlock(this)">+ add block</button>
  `;
  container.appendChild(div);
  div.querySelector('.qe-session-name').focus();
  addQEBlock(div.querySelector('.qe-add-block'));
}
```

- [ ] **Step 2: Verify manually**

Reload. Click Quick Entry tab → click "+ Add Session".
Expected: a session row appears with name input focused, a block row below it, and an exercise row inside the block.
Click × on the session row — session disappears.

- [ ] **Step 3: Commit**
```bash
git add templates/cms.html
git commit -m "feat: quick entry — add/remove session rows"
```

---

### Task 3: Add / remove block rows with auto-labelling

**Files:**
- Modify: `templates/cms.html` (JS section)

**Interfaces:**
- Consumes: `.qe-session` (from Task 2)
- Produces: `addQEBlock(btn)` — appends a `.qe-block` div to the session's `.qe-blocks`
- Produces: `updateQEBlockLabels(sessionEl)` — re-letters blocks A, B, C… after removal

- [ ] **Step 1: Add block functions**

Directly after `addQESession`, add:

```js
function addQEBlock(btn) {
  const session = btn.closest('.qe-session');
  const blocksContainer = session.querySelector('.qe-blocks');
  const idx = blocksContainer.querySelectorAll('.qe-block').length;
  const label = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[idx] || String.fromCharCode(65 + idx);
  const div = document.createElement('div');
  div.className = 'qe-block';
  div.innerHTML = `
    <div class="qe-block-row">
      <span class="qe-block-label">Block ${label}</span>
      <input type="text" class="qe-block-focus"
             placeholder="Block focus e.g. Strength / Power" />
      <button class="btn btn-red qe-remove"
              onclick="const s=this.closest('.qe-session');
                       this.closest('.qe-block').remove();
                       updateQEBlockLabels(s);">×</button>
    </div>
    <div class="qe-exercises"></div>
    <button class="qe-add-ex" onclick="addQEExercise(this)">+ add exercise</button>
  `;
  blocksContainer.appendChild(div);
  addQEExercise(div.querySelector('.qe-add-ex'));
}

function updateQEBlockLabels(sessionEl) {
  const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  sessionEl.querySelectorAll('.qe-block').forEach((block, i) => {
    block.querySelector('.qe-block-label').textContent =
      'Block ' + (ALPHA[i] || String.fromCharCode(65 + i));
  });
}
```

- [ ] **Step 2: Verify manually**

Click Quick Entry → "+ Add Session" → click "+ add block" twice.
Expected: blocks labelled "Block A", "Block B".
Remove Block A — remaining block relabels to "Block A".

- [ ] **Step 3: Commit**
```bash
git add templates/cms.html
git commit -m "feat: quick entry — add/remove block rows with auto-labels"
```

---

### Task 4: Exercise rows + keyboard flow

**Files:**
- Modify: `templates/cms.html` (JS section)

**Interfaces:**
- Consumes: `.qe-block` (from Task 3), `.qe-session-format` select value
- Produces: `addQEExercise(btn)` — appends a `.qe-exercise` row, returns the new element
- Produces: keyboard handlers `qeEnterNext`, `qeTabNext` wired to exercise inputs

- [ ] **Step 1: Add exercise functions**

Directly after `updateQEBlockLabels`, add:

```js
function addQEExercise(btn) {
  const block = btn.closest('.qe-block');
  const exContainer = block.querySelector('.qe-exercises');
  const isCardio = btn.closest('.qe-session')
                      .querySelector('.qe-session-format').value === 'cardio';
  const div = document.createElement('div');
  div.className = 'qe-exercise' + (isCardio ? ' cardio' : '');
  if (isCardio) {
    div.innerHTML = `
      <input type="text" class="qe-ex-name" placeholder="e.g. Ski Erg"
             onkeydown="qeEnterNext(event,this)" />
      <input type="text" class="qe-ex-sets" placeholder="200 cal"
             onkeydown="qeTabNext(event,this)" />
      <button class="btn btn-red qe-remove"
              onclick="this.closest('.qe-exercise').remove()">×</button>
    `;
  } else {
    div.innerHTML = `
      <input type="text" class="qe-ex-code" placeholder="A1" />
      <input type="text" class="qe-ex-name" placeholder="Exercise name"
             onkeydown="qeEnterNext(event,this)" />
      <input type="text" class="qe-ex-sets" placeholder="4×8"
             onkeydown="qeTabNext(event,this)" />
      <button class="btn btn-red qe-remove"
              onclick="this.closest('.qe-exercise').remove()">×</button>
    `;
  }
  exContainer.appendChild(div);
  return div;
}

function qeEnterNext(e, input) {
  if (e.key !== 'Enter') return;
  e.preventDefault();
  const newRow = addQEExercise(input.closest('.qe-block').querySelector('.qe-add-ex'));
  newRow.querySelector('.qe-ex-name').focus();
}

function qeTabNext(e, input) {
  if (e.key !== 'Tab' || e.shiftKey) return;
  e.preventDefault();
  const newRow = addQEExercise(input.closest('.qe-block').querySelector('.qe-add-ex'));
  newRow.querySelector('.qe-ex-name').focus();
}
```

- [ ] **Step 2: Verify keyboard flow**

Open Quick Entry → "+ Add Session".
Type a session name. Click the exercise name field in Block A.
Type `Back Squat` → Tab → type `4×6` → Tab.
Expected: a new exercise row appears and the cursor is in its name field.
Type `Romanian DL` → Enter.
Expected: another new row appears.

- [ ] **Step 3: Verify cardio format**

Change the session format dropdown to "Cardio / Class".
Click "+ add block".
Expected: exercise rows have no code field (two inputs only: name + target).

- [ ] **Step 4: Commit**
```bash
git add templates/cms.html
git commit -m "feat: quick entry — exercise rows and keyboard flow"
```

---

### Task 5: Save All

**Files:**
- Modify: `templates/cms.html` (JS section)

**Interfaces:**
- Consumes: `#qe-container` DOM tree (sessions → blocks → exercises from Tasks 2–4)
- Consumes: `POST /api/sessions` — payload `{ name, coach_notes, session_type, blocks: [{label, focus, exercises:[{code,name,sets_reps}]}] }`
- Consumes: `switchTab(name)` — existing function
- Consumes: `loadSessions()` — existing function

- [ ] **Step 1: Add `saveAllQESessions`**

Directly after `addQEExercise`/`qeTabNext`, add:

```js
async function saveAllQESessions() {
  const sessionEls = document.querySelectorAll('#qe-container .qe-session');
  const toSave = [];

  sessionEls.forEach(sessionEl => {
    const name = sessionEl.querySelector('.qe-session-name').value.trim();
    if (!name) return;

    const blocks = [];
    const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    sessionEl.querySelectorAll('.qe-block').forEach((blockEl, i) => {
      const label = ALPHA[i] || String.fromCharCode(65 + i);
      const focus = blockEl.querySelector('.qe-block-focus').value.trim();
      const exercises = [];
      blockEl.querySelectorAll('.qe-exercise').forEach(exEl => {
        const exName = exEl.querySelector('.qe-ex-name').value.trim();
        if (!exName) return;
        exercises.push({
          code:      exEl.querySelector('.qe-ex-code')?.value.trim() || '',
          name:      exName,
          sets_reps: exEl.querySelector('.qe-ex-sets')?.value.trim() || ''
        });
      });
      if (exercises.length) blocks.push({ label, focus, exercises });
    });

    toSave.push({
      name,
      coach_notes:  sessionEl.querySelector('.qe-session-notes').value.trim(),
      session_type: sessionEl.querySelector('.qe-session-format').value,
      blocks
    });
  });

  if (!toSave.length) {
    alert('No sessions to save — add at least one session with a name.');
    return;
  }

  const btn = document.getElementById('qe-save-btn');
  btn.disabled = true;
  btn.textContent = 'Saving…';

  let saved = 0;
  for (const payload of toSave) {
    const r = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (r.ok) saved++;
  }

  btn.disabled = false;
  btn.textContent = 'Save All';
  document.getElementById('qe-container').innerHTML = '';
  loadSessions();
  switchTab('library');
  alert(`${saved} session${saved !== 1 ? 's' : ''} saved.`);
}
```

- [ ] **Step 2: End-to-end manual test**

Open Quick Entry. Add two sessions:

Session 1 — "Monday S&C", Strength:
- Block A, focus "Strength/Power": Back Squat · A1 · 4×6; Romanian DL · A2 · 3×10
- Block B, focus "Conditioning": Assault Bike · B1 · 15 cal

Session 2 — "Tuesday Cardio", Cardio / Class:
- Block A: Ski Erg · 200 cal; Sled Push · 20m

Click "Save All".
Expected: alert says "2 sessions saved", Library tab opens showing both new sessions.
Click Edit on "Monday S&C" — verify blocks and exercises are all present.

- [ ] **Step 3: Test skipping blank sessions**

Open Quick Entry → "+ Add Session" (leave name blank) → click "Save All".
Expected: alert says "No sessions to save".

- [ ] **Step 4: Run backend tests to confirm no regression**
```bash
cd /Users/ewantaylormacbookair/Projects/cs-fitness && pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**
```bash
git add templates/cms.html
git commit -m "feat: quick entry — Save All posts sessions to API"
```
