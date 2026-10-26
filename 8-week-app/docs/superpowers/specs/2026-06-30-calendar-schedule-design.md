# Calendar Schedule — Design Spec
**Date:** 2026-06-30  
**Status:** Approved

---

## Problem

The current Schedule tab uses a repeating weekly time-slot grid (day_of_week + time → session). This doesn't match the gym's actual workflow: sessions are planned date-specifically in TrainHeroic and need to be mirrored in the CS Fitness app for the same dates.

---

## Goal

Replace the Schedule tab with a date-specific weekly calendar view that mirrors TrainHeroic's coach calendar. One session per day. Ad-hoc overrides via the existing Now Playing tab.

---

## Data Model

### New table: `calendar`

```sql
CREATE TABLE IF NOT EXISTS calendar (
  date       TEXT PRIMARY KEY,   -- ISO date e.g. '2026-06-29'
  session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL
);
```

One row per day. The existing `schedule` table is retained in the database but no longer used by the display logic.

---

## API

### `GET /api/calendar`
Query params: `start` (ISO date), `end` (ISO date, inclusive).  
Returns a list of assigned days with full session detail:
```json
[
  {
    "date": "2026-06-29",
    "session_id": 3,
    "name": "CS Performance - Mon 29 Jun | Lower + Conditioning",
    "coach_notes": "Lower + conditioning",
    "blocks": [ ... ]
  }
]
```

### `POST /api/calendar`
Body: `{ "date": "2026-06-29", "session_id": 3 }`  
Inserts or replaces the assignment for that date. Returns `{ "ok": true }`.

### `DELETE /api/calendar/<date>`
Removes the assignment for the given date. Returns 204.

All three endpoints require authentication (`@require_auth`).

---

## `get_current_session()` — updated priority

1. **Manual override** — check `override` table (existing behaviour)
2. **Today's calendar entry** — look up today's ISO date in `calendar` table
3. **Return null** — TV shows idle/blank

The old day_of_week + time walk-back logic is removed entirely.

---

## Calendar UI (Schedule tab)

### Header
- Month and year label: `< June 2026 >`
- Left/right arrows advance the view by 7 days
- Current week shown by default on load
- Today's column header highlighted with green accent

### Day columns
Seven columns: Sun → Sat, each headed with day name + date number (e.g. "MON 29").

### Day cell — assigned session
- Session name (bold, white)
- Exercise list: each block shown as `[A] Exercise name · sets_reps`
- **Change** button → inline dropdown of all library sessions, auto-saves on selection
- **Remove** link → clears the assignment, no confirmation needed

### Day cell — empty
- Faint `+ Assign` button
- Opens an inline dropdown of all library sessions
- Selecting one assigns it immediately (POST /api/calendar)

### Styling
- Existing dark theme: `#000` background, `#3DFF4F` green accents, `Inter` font
- Assigned cells: `#0d1f0d` background with green left border (matches current "on screen" card style)
- Empty cells: `#0a0a0a` background, dashed border

---

## Now Playing tab

No changes. Manual override (Publish Now / Clear Override) continues to work as before and takes priority over the calendar.

---

## Out of scope

- TV on/off logic — handled separately by `tv_control.py` + Task Scheduler
- Multi-session days (gym only needs one session per day)
- Drag-and-drop reordering
- The old repeating weekly schedule UI

---

## Files changed

| File | Change |
|------|--------|
| `database.py` | Add `calendar` table to schema; add migration guard |
| `app.py` | Add 3 calendar API endpoints; update `get_current_session()` |
| `templates/cms.html` | Replace Schedule tab content with calendar view |
