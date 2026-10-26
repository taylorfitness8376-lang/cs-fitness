# Quick Entry — Design Spec
**Date:** 2026-06-17
**Project:** CS Fitness CMS (`/Users/ewantaylormacbookair/Projects/cs-fitness`)

## Context

Workouts are authored in TrainHeroic and need to be manually transcribed into the CS Fitness CMS. The current editor handles one session at a time with multiple clicks per block/exercise. This is too slow when entering a full week of sessions in one sitting with a phone open on the side.

## Goal

A spreadsheet-style bulk entry tab that lets the coach transcribe multiple sessions quickly, using only the keyboard.

## Scope

- New "Quick Entry" tab in the CMS (5th tab, after Now Playing)
- Entry of new sessions only — editing existing sessions stays in the Library/Editor
- No changes to existing tabs, API routes, or data model

## UI Layout

A single scrollable column of three visually distinct row types:

```
[+ Add Session]                              [Save All]

━━ SESSION  [Name              ]  [Strength ▾]  [Notes...]  [×]
   ─ BLOCK  A  [Focus          ]                            [×]
        EX  A1 [Exercise name  ]  [Sets/reps ]              [×]
        EX  A2 [Exercise name  ]  [Sets/reps ]              [×]
              [+ add exercise  ]
   ─ BLOCK  B  [Focus          ]                            [×]
        EX     [Exercise name  ]  [Sets/reps ]              [×]
              [+ add exercise  ]
   [+ add block]
━━ SESSION  [Name              ]  [Cardio ▾  ]  [Notes...]  [×]
   ...

[+ Add Session]
```

### Row types

**Session row** — heavier top border, dark background tint. Fields: name (text), format (Strength / Cardio dropdown), coach notes (text). [×] removes the session and all its blocks/exercises.

**Block row** — indented one level. Block letter (A, B, C…) is displayed but not editable — auto-assigned in order. Fields: focus (text, e.g. "Strength/Power"). [×] removes the block and its exercises.

**Exercise row** — indented two levels. Fields: code (text, optional, e.g. "A1"), name (text), sets/reps (text). [×] removes the exercise.

### Keyboard flow

- Tab moves right across fields within an exercise row
- Tab from the sets/reps field (last field) creates a new exercise row below and focuses its name field
- Enter from any exercise name field also creates a new exercise row
- This allows entry of a full block without touching the mouse: type name → Tab → type sets/reps → Tab → next exercise

## Save behaviour

**Save All** button (top right, green):
- Iterates through all sessions in the view
- Skips any session with a blank name
- POSTs each valid session to the existing `POST /api/sessions` endpoint (same payload as the editor)
- On completion: clears the quick entry view, switches to the Library tab, shows a count ("3 sessions saved")
- No auto-save — explicit only, so a full week can be built before committing

**Discard** (implicit — navigating away without saving): the in-progress entries are lost. No confirmation dialog needed since nothing has been written to the DB.

## Implementation

### Files changed

- `templates/cms.html` — add Quick Entry panel HTML + JS
- No backend changes required (reuses existing `POST /api/sessions`)

### JS state

```js
// Array of session objects built in-memory
quickSessions = [
  {
    name: "",
    format: "strength",
    coach_notes: "",
    blocks: [
      {
        focus: "",
        exercises: [{ code: "", name: "", sets_reps: "" }]
      }
    ]
  }
]
```

State is held only in the DOM (no separate JS array needed) — read from input values at save time by walking the DOM tree.

### DOM structure

```html
<div class="qe-session">
  <!-- session fields -->
  <div class="qe-block">
    <!-- block fields -->
    <div class="qe-exercise"><!-- exercise fields --></div>
    <button>+ add exercise</button>
  </div>
  <button>+ add block</button>
</div>
```

Block letters are computed at save time by counting `.qe-block` siblings — no need to track them in state.

### Styling

Follows existing CMS design tokens:
- Session row: `background: #0a0a0a`, `border-top: 2px solid #2a2a2a`
- Block row: `background: #0d0d0d`, left indent `1.5rem`
- Exercise row: `background: transparent`, left indent `3rem`
- Matches existing `.btn-dark`, `.btn-green`, `input`, `select` styles

## Out of scope

- Editing existing sessions (use Library → Editor)
- Auto-save or draft persistence
- Reordering sessions/blocks/exercises by drag
- Importing directly from TrainHeroic (no public API available)
