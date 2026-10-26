# Schedule tab: "Publish Now" button on calendar cells

## Problem

To push a specific day's workout onto the TV right now (overriding whatever
the calendar says for today), you have to leave the Schedule tab, go to the
Now Playing tab, find the session in a dropdown, and click "Publish Now".
There's no way to do this directly from the Schedule tab where you're
already looking at the workout you want.

## Design

Add a "Publish Now" button to each *assigned* calendar cell in the Schedule
tab (`templates/cms.html`, `cal-cell-actions` block), alongside the existing
"Change..." dropdown and "Remove" button. Empty cells get no such button —
there's nothing to publish.

Clicking it calls the existing `publishSession(id)` function and `/api/publish`
endpoint — the same override mechanism already used by the Library tab's
"Publish Now" button. No backend or API changes are needed.

Behavior follows the existing override semantics exactly: the click pushes
that session live immediately, and the override expires at the end of the
current real-world day (not the day the workout was originally scheduled
for). So clicking "Publish Now" on a future day's cell shows that workout
right now, and falls back to the calendar's normal entry for today once the
day rolls over (or if manually cleared from Now Playing).

Feedback on click matches the existing pattern: `alert("Published!")`, same
as the Library tab button.

## Out of scope

- No confirmation dialog before publishing (matches existing "Publish Now"
  buttons elsewhere in the app, which also fire immediately).
- No visual indicator on the calendar showing which cell is currently live
  on the TV — that already exists on the Now Playing tab.
