# CS Fitness — Gym Owner Guide

---

## First-Time Setup (do once)

### 1. Copy the folder
Extract the zip and copy the `cs-fitness` folder to:
```
C:\CSFitness\cs-fitness\
```
Do **not** put it in OneDrive, Downloads, or Desktop — these cause path problems.

### 2. Run the setup script
Right-click **`SETUP TV SCHEDULE.bat`** → **Run as administrator**.

This will:
- Download NSSM and install the app as a silent Windows Service (auto-starts on boot, restarts if it crashes — no console window to accidentally close)
- Schedule the TV to turn **on at 04:00** and **off at 22:00** every day

When it finishes, the app is running. You can confirm at: **http://localhost:9090/cms**

### 3. Log in and import sessions
1. Open a browser and go to **http://localhost:9090/cms**
2. Password: **csfit2024**
3. Go to the **Library** tab → click **↑ Import**
4. Select the file `data/cs_performance_import.json` from the cs-fitness folder
5. Your sessions will appear in the Library

### 4. Assign sessions to the calendar
1. Go to the **Schedule** tab
2. Navigate to the current week using the **‹ ›** arrows
3. Under each day, click **+ Assign session** and pick the session from the dropdown
4. It saves instantly — no Save button needed

### 5. Set up the TV (once only)
1. Turn the TV on with the remote
2. Press **Home** → open the **Internet** browser app
3. Type this address: **http://192.168.3.132:9090/display**
4. In the browser settings, set this as the homepage
5. The workout screen will now load automatically every time the browser opens

---

## Daily Operation

The app runs automatically — nothing to do each day.

| Time | What happens |
|------|-------------|
| 04:00 | TV turns on, browser loads today's workout |
| Any time | If you publish a session manually it appears on TV within 10 seconds |
| 22:00 | TV turns off |

If the PC restarts overnight, the app starts itself automatically (Windows Service).

---

## Managing Sessions

### Creating a new session
1. Go to **Library** → click **+ New Session**
2. Give it a name (e.g. "Monday S&C")
3. Choose a format: **Strength** (sets × reps) or **Cardio / Class** (distances / times)
4. Add a **Coach's Notes** line — shown as a banner on the TV
5. Add blocks and exercises
6. Click **Save Session**

### Editing a session
Library → find the session → click **Edit** → make changes → **Save Session**

### Deleting a session
Library → click **Delete** on the session card. Cannot be undone.

### Importing sessions from a JSON file
Library → **↑ Import** → select a `.json` file. Sessions already in the library (same name) are skipped.

### Exporting all sessions
Library → **↓ Export** — downloads a JSON file you can import on another machine.

---

## Schedule (Calendar)

The Schedule tab shows a weekly calendar view — one session per day.

- **Navigate weeks:** use the **‹ ›** arrows in the header
- **Assign a session:** click **+ Assign session** under an empty day and pick from the dropdown
- **Change a session:** click the **Change...** dropdown on an assigned day
- **Remove a session:** click **Remove** on an assigned day
- Changes save instantly

Today's date is highlighted in green. The TV always shows the session assigned to today's date.

---

## Now Playing

Use the **Now Playing** tab to:
- See what is currently showing on the TV
- **Manually override** — push any session to the TV immediately, regardless of the schedule
- **Clear override** — return to the scheduled session for today

---

## TV Control

The TV turns on and off automatically via the scheduled tasks set up during installation.

To control it manually:
- **Turn TV on:** double-click `tv_on.bat`
- **Turn TV off:** double-click `tv_off.bat`

The TV must have **Quick Start+** enabled (Settings → General → System Manager → Quick Start+) so it stays on standby and can be woken over the network.

---

## Managing the Windows Service

The app runs as a Windows Service called **"CS Fitness Display Server"**. To manage it:

1. Press **Win + R** → type `services.msc` → press Enter
2. Find **CS Fitness Display Server** in the list
3. Right-click to Start / Stop / Restart

Logs are saved to `cs-fitness\logs\service.log` if you need to diagnose a problem.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| TV shows blank page | Open `services.msc` and check CS Fitness Display Server is Running |
| Can't reach CMS | Go to http://localhost:9090/cms — check the service is running |
| TV can't load the page | Make sure TV and PC are on the same WiFi network |
| Wrong session on TV | Check the Schedule tab — make sure today's date has the right session assigned |
| TV not turning on at 04:00 | Check Quick Start+ is enabled on the TV; check Task Scheduler for CSFitness_TV_On |

---

## Quick Reference

| What | Where |
|------|-------|
| CMS | http://localhost:9090/cms |
| TV Display | http://192.168.3.132:9090/display |
| Password | csfit2024 |
| Service logs | cs-fitness\logs\service.log |
| Setup script | SETUP TV SCHEDULE.bat (run as Administrator) |
