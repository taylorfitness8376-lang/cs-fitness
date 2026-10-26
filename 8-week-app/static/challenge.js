function getTodayIsoDate() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function getOffsetIsoDate(baseIso, deltaDays) {
  const parts = (baseIso || getTodayIsoDate()).split("-").map(Number);
  const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2] + deltaDays));
  return dt.toISOString().slice(0, 10);
}

function formatHumanDate(isoStr) {
  const todayIso = getTodayIsoDate();
  const yestIso = getOffsetIsoDate(todayIso, -1);
  const tomIso = getOffsetIsoDate(todayIso, 1);
  const parts = (isoStr || todayIso).split("-").map(Number);
  const dt = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
  const shortStr = dt.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  if (isoStr === todayIso) return `${shortStr} · TODAY`;
  if (isoStr === yestIso) return `${shortStr} · Yesterday`;
  if (isoStr === tomIso) return `${shortStr} · Tomorrow`;
  return shortStr;
}

let STATE = {
  date: getTodayIsoDate(),
  autoFollowToday: true,
  overview: null,
  workoutsData: null,
  restTimerId: null,
  restSecondsLeft: 0,
};
window.STATE = STATE;

function showToast(msg) {
  const el = document.getElementById("app-toast");
  if (!el) return;
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => {
    el.style.display = "none";
  }, 2600);
}

function switchTab(tabName) {
  if (typeof window.setOnePagerMode === "function") {
    const dView = document.getElementById("onepager-daily-view");
    const wView = document.getElementById("onepager-weekly-view");
    if ((dView && dView.style.display === "block") || (wView && wView.style.display === "block")) {
      window.setOnePagerMode("full");
    }
  }
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === "panel-" + tabName);
  });
  if (tabName === "workouts" && !STATE.workoutsData) {
    loadWorkouts();
  } else if (tabName === "checkin") {
    const sel = document.getElementById("ci-week-select");
    loadWeekSheet(sel ? sel.value : "0");
  } else if (tabName === "integrations" || tabName === "coach") {
    runCoachCalculator(false);
    loadCohortBoard();
    loadWhatsAppFeed();
  }
}

function setQuickDate(dateStr) {
  STATE.autoFollowToday = dateStr === getTodayIsoDate();
  const dateInput = document.getElementById("active-date");
  if (dateInput) dateInput.value = dateStr;
  loadOverview(dateStr);
}

function goToToday() {
  setQuickDate(getTodayIsoDate());
}

function goToYesterday() {
  setQuickDate(getOffsetIsoDate(getTodayIsoDate(), -1));
}

function stepActiveDate(deltaDays) {
  const curr = STATE.date || getTodayIsoDate();
  setQuickDate(getOffsetIsoDate(curr, deltaDays));
}

function renderHeaderWeekStrip(sheet, activeDate) {
  const strip = document.getElementById("hdr-week-strip");
  if (!strip || !sheet || !sheet.rows) return;
  const todayIso = getTodayIsoDate();
  strip.innerHTML = sheet.rows
    .map((r) => {
      const isSelected = r.date === activeDate;
      const isToday = r.date === todayIso;
      const hasData = (r.steps || 0) > 0 || (r.calories || 0) > 0 || r.weight_kg != null;
      const dayNum = r.date.slice(8, 10);
      const bg = isSelected ? "rgba(61,255,79,0.18)" : "#0b110d";
      const border = isSelected ? "2px solid var(--green)" : isToday ? "1px dashed var(--green)" : "1px solid var(--border)";
      return `<button type="button" onclick="setQuickDate('${r.date}')" style="cursor:pointer;background:${bg};border:${border};border-radius:9px;padding:0.35rem 0.2rem;text-align:center;color:#fff">
        <div style="font-size:0.65rem;color:${isToday ? "var(--green)" : "var(--muted)"};font-weight:800">${r.day_short}${isToday ? " • TODAY" : ""}</div>
        <div style="font-size:0.82rem;font-weight:800;margin-top:1px">${dayNum} ${hasData ? '<span style="color:var(--green);font-size:0.68rem">✓</span>' : ""}</div>
      </button>`;
    })
    .join("");
}

async function loadOverview(dateOverride) {
  const dateInput = document.getElementById("active-date");
  const todayIso = getTodayIsoDate();
  const yestIso = getOffsetIsoDate(todayIso, -1);
  const targetDate = dateOverride || (dateInput && dateInput.value) || STATE.date || todayIso;
  STATE.date = targetDate;
  if (dateInput) dateInput.value = targetDate;

  const humanEl = document.getElementById("hdr-date-human");
  if (humanEl) humanEl.textContent = formatHumanDate(targetDate);
  const opLbl = document.getElementById("op-date-lbl");
  if (opLbl) opLbl.textContent = formatHumanDate(targetDate);

  const btnToday = document.getElementById("btn-date-today");
  const btnYest = document.getElementById("btn-date-yesterday");
  if (btnToday) {
    btnToday.className = "btn btn-sm" + (targetDate === todayIso ? " btn-green" : "");
    btnToday.textContent = targetDate === todayIso ? "● Today" : "↩ Today";
  }
  if (btnYest) {
    btnYest.className = "btn btn-sm" + (targetDate === yestIso ? " btn-green" : "");
  }

  const res = await fetch(`/api/challenge/overview?date=${encodeURIComponent(targetDate)}`);
  const data = await res.json();
  STATE.overview = data;
  renderTodayDashboard(data);
  renderIntegrationsAndStaples(data);

  // Automatically sync Check-In Sheet, Workouts & 1-Pager week selectors with the active date's week!
  const sheetWk = data.week_info && data.week_info.sheet_week_num != null ? data.week_info.sheet_week_num : 0;
  const ciSel = document.getElementById("ci-week-select");
  if (ciSel) ciSel.value = String(sheetWk);
  const opWkSel = document.getElementById("op-week-select");
  if (opWkSel) opWkSel.value = String(sheetWk);
  const wkSel = document.getElementById("wk-week-select");
  if (wkSel && sheetWk >= 1) wkSel.value = String(sheetWk);
  if (data.current_week_sheet) {
    renderHeaderWeekStrip(data.current_week_sheet, targetDate);
    renderWeekSheetData(data.current_week_sheet);
  }
}

function renderTodayDashboard(data) {
  const p = data.profile;
  const c = data.checkin;
  const wk = data.week_info;
  const wtd = data.win_the_day;

  document.getElementById("hdr-phase").textContent = `${wk.phase} · Min ${wk.step_target.toLocaleString()} steps · ${p.target_calories.toLocaleString()} kcal`;
  document.getElementById("hdr-score").textContent = `Win the Day: ${wtd.score}/100`;

  document.getElementById("td-client-name").textContent = p.client_name;
  document.getElementById("td-start-weight").textContent = `${p.start_weight_kg}kg (${p.start_body_fat_pct}% BF)`;
  document.getElementById("td-target-weight").textContent = `${p.target_weight_kg}kg (${p.target_body_fat_pct}% BF)`;
  document.getElementById("td-lbm").textContent = `${p.lean_body_mass_kg}kg`;

  // Sync badges
  document.getElementById("badge-garmin-sync").textContent =
    c.sync_source_garmin ? `⌚ ${c.sync_source_garmin}` : "⌚ Garmin: Ready";
  document.getElementById("badge-mfp-sync").textContent = "🥗 Nutrition: Add Manually";

  // 1. Steps
  const steps = c.steps || 0;
  const stepTarget = wk.step_target || 10000;
  document.getElementById("td-steps-val").textContent = steps.toLocaleString();
  document.getElementById("td-steps-target").textContent = stepTarget.toLocaleString();
  document.getElementById("bar-steps").style.width = `${Math.min(100, Math.round((steps / stepTarget) * 100))}%`;
  const stepsBadge = document.getElementById("steps-status-badge");
  stepsBadge.textContent = steps >= stepTarget ? "GREEN ✅" : `${Math.max(0, stepTarget - steps).toLocaleString()} to go`;
  stepsBadge.className = "badge " + (steps >= stepTarget ? "badge-green" : "badge-red");

  // 2. Calories & Macros
  const cals = c.calories || 0;
  document.getElementById("td-cals-val").textContent = cals.toLocaleString();
  document.getElementById("td-cals-target").textContent = p.target_calories.toLocaleString();
  document.getElementById("bar-cals").style.width = `${Math.min(100, Math.round((cals / p.target_calories) * 100))}%`;
  document.getElementById("td-carbs-val").textContent = c.carbs_g || 0;
  document.getElementById("td-carbs-target").textContent = p.target_carbs_g;
  document.getElementById("td-fats-val").textContent = c.fats_g || 0;
  document.getElementById("td-fats-target").textContent = p.target_fats_g;
  document.getElementById("td-fibre-val").textContent = c.fibre_g || 0;

  // 3. Protein & Water
  const prot = c.protein_g || 0;
  const water = c.water_l || 0;
  document.getElementById("td-prot-val").textContent = prot;
  document.getElementById("td-prot-target").textContent = p.target_protein_g;
  document.getElementById("td-water-val").textContent = Number(water).toFixed(2);
  document.getElementById("td-water-target").textContent = p.target_water_l;
  document.getElementById("bar-prot").style.width = `${Math.min(100, Math.round((prot / p.target_protein_g) * 100))}%`;

  // Form inputs
  document.getElementById("in-weight").value = c.weight_kg != null ? c.weight_kg : "";
  document.getElementById("in-weigh-time").value = c.weigh_time || "06:30";
  document.getElementById("td-rolling-weight").textContent = `${Number(data.rolling_7d_weight_kg || p.start_weight_kg).toFixed(2)} kg`;
  document.getElementById("in-training-type").value = c.training_type || "REST";
  document.getElementById("in-stick-plan").value = c.stick_to_plan || "Y";
  document.getElementById("in-steps").value = steps;
  document.getElementById("in-calories").value = cals;
  document.getElementById("in-protein").value = prot;
  if (document.getElementById("in-water")) document.getElementById("in-water").value = water;
  if (document.getElementById("in-carbs")) document.getElementById("in-carbs").value = c.carbs_g || 0;
  if (document.getElementById("in-fats")) document.getElementById("in-fats").value = c.fats_g || 0;
  if (document.getElementById("in-fibre")) document.getElementById("in-fibre").value = c.fibre_g || 0;
  document.getElementById("in-sleep").value = c.sleep_str || "";
  document.getElementById("in-notes").value = c.notes || "";
  document.getElementById("in-mindset").value = c.mindset_win || "";

  // Garmin recovery metrics
  document.getElementById("td-sleep-score").textContent = c.sleep_score != null ? `${c.sleep_score}/100` : "—";
  document.getElementById("td-body-battery").textContent = c.body_battery != null ? `${c.body_battery}%` : "—";
  document.getElementById("td-rhr").textContent = c.resting_hr != null ? `${c.resting_hr} bpm` : "—";

  // Populate CS Class dropdown
  const clsSel = document.getElementById("in-cs-class");
  if (clsSel && clsSel.options.length <= 1) {
    (data.cs_timetable || []).forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = `${item.name} → [${item.training_type}]`;
      clsSel.appendChild(opt);
    });
  }

  // Populate Staple Quick Select
  const stSel = document.getElementById("quick-staple-select");
  if (stSel && stSel.options.length === 0) {
    (data.staple_meals || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `[${m.slot}] ${m.name} (${m.calories} kcal · ${m.protein_g}g P)`;
      stSel.appendChild(opt);
    });
  }

  // Habits
  [
    "morning_steps_banked",
    "checkpoint_12pm_5k",
    "checkpoint_5pm_10k",
    "caffeine_cutoff_met",
    "electrolytes_taken",
  ].forEach((key) => {
    const done = Boolean(c[key]);
    const rowEl = document.getElementById("hab-" + key);
    const bEl = document.getElementById("hab-badge-" + key);
    if (rowEl) rowEl.classList.toggle("done", done);
    if (bEl) {
      bEl.textContent = done ? "Done ✅" : "Tap to mark";
      bEl.className = "badge " + (done ? "badge-green" : "");
    }
  });

  // Visual WhatsApp Share Card
  document.getElementById("sc-date").textContent = `${data.date} · ${wk.phase}`;
  document.getElementById("sc-steps").textContent = steps.toLocaleString();
  document.getElementById("sc-prot").textContent = `${prot}g`;
  document.getElementById("sc-cals").textContent = cals.toLocaleString();
  document.getElementById("sc-water").textContent = `${Number(water).toFixed(2)}L`;
  if (data.whatsapp_share) {
    document.getElementById("wa-caption-box").value = data.whatsapp_share.caption;
    document.getElementById("wa-direct-link").href = data.whatsapp_share.whatsapp_url;
  }

  renderDailyActivities(data.daily_activities || [], c);
}

function renderDailyActivities(activities, checkin) {
  const listEl = document.getElementById("today-activities-list");
  const badgeEl = document.getElementById("td-act-summary-badge");
  if (badgeEl && checkin) {
    badgeEl.textContent = `${checkin.training_type || "REST"}${checkin.class_attended ? " · " + checkin.class_attended : ""}`;
  }
  if (!listEl) return;
  if (!activities.length) {
    listEl.innerHTML = `<div style="font-size:0.75rem;color:var(--muted);padding:0.45rem 0">No workouts or Garmin runs logged for ${STATE.date} yet — add a Gym Class / Strength workout or Garmin Run below.</div>`;
    return;
  }
  listEl.innerHTML = activities
    .map((a) => {
      const isRun = a.distance_km && a.distance_km > 0;
      const stats = [];
      if (a.start_time) stats.push(`🕒 ${a.start_time}`);
      if (a.duration_mins) stats.push(`⏱️ ${a.duration_mins} min`);
      if (isRun) stats.push(`📍 <strong>${a.distance_km} km</strong>`);
      if (a.pace_str) stats.push(`⚡ <strong>${a.pace_str}</strong>`);
      if (a.avg_hr) stats.push(`❤️ Avg ${a.avg_hr}${a.max_hr ? " / Max " + a.max_hr : ""} bpm`);
      if (a.calories) stats.push(`🔥 ${a.calories} kcal`);
      if (a.elevation_m) stats.push(`⛰️ +${a.elevation_m}m`);
      if (a.steps) stats.push(`👟 ${Number(a.steps).toLocaleString()} steps`);
      return `<div class="habit-item done" style="cursor:default;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center;gap:0.65rem">
        <div style="flex:1">
          <div style="font-size:0.8rem;font-weight:700;color:#fff">
            <span class="badge ${a.category === "GYM" ? "badge-green" : "badge-blue"}">${a.category}</span>
            <span class="badge" style="margin-left:0.25rem">${a.source}</span>
            ${a.title}
          </div>
          <div style="font-size:0.72rem;color:var(--muted);margin-top:0.2rem">${stats.join(" · ")}${a.notes ? " — " + a.notes : ""}</div>
        </div>
        <button class="btn btn-sm" style="background:rgba(248,113,113,0.14);color:#f87171;border:1px solid rgba(248,113,113,0.4);padding:0.25rem 0.55rem;font-size:0.72rem;flex-shrink:0" onclick="deleteDailyActivity(${a.id})" title="Delete this workout / Garmin activity">🗑️ Delete</button>
      </div>`;
    })
    .join("");
}

async function deleteDailyActivity(activityId) {
  if (!activityId) return;
  const res = await fetch(`/api/challenge/activities/${encodeURIComponent(activityId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
  const out = await res.json();
  if (!res.ok || !out.ok) {
    showToast(`⚠️ Could not delete workout: ${out.error || "Unknown error"}`);
    return;
  }
  await loadOverview(STATE.date);
  if (typeof window.loadProgressSummary === "function") {
    await window.loadProgressSummary();
  }
  const sel = document.getElementById("ci-week-select");
  if (sel) await loadWeekSheet(sel.value || "0");
  showToast(`🗑️ Deleted "${out.deleted.title}" (${out.training_type || "REST"})`);
}
window.deleteDailyActivity = deleteDailyActivity;

async function postCheckinUpdate(payload, toastMsg) {
  payload.date = STATE.date;
  const res = await fetch("/api/challenge/checkins", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await res.json();
  await loadOverview(STATE.date);
  if (toastMsg) showToast(toastMsg);
}

async function saveTodayCheckin() {
  const payload = {
    weight_kg: document.getElementById("in-weight").value ? parseFloat(document.getElementById("in-weight").value) : null,
    weigh_time: document.getElementById("in-weigh-time").value,
    training_type: document.getElementById("in-training-type").value,
    stick_to_plan: document.getElementById("in-stick-plan").value,
    steps: parseInt(document.getElementById("in-steps").value || "0", 10),
    calories: parseInt(document.getElementById("in-calories").value || "0", 10),
    protein_g: parseInt(document.getElementById("in-protein").value || "0", 10),
    water_l: document.getElementById("in-water") ? parseFloat(document.getElementById("in-water").value || "0") : undefined,
    carbs_g: document.getElementById("in-carbs") ? parseInt(document.getElementById("in-carbs").value || "0", 10) : undefined,
    fats_g: document.getElementById("in-fats") ? parseInt(document.getElementById("in-fats").value || "0", 10) : undefined,
    fibre_g: document.getElementById("in-fibre") ? parseInt(document.getElementById("in-fibre").value || "0", 10) : undefined,
    sleep: document.getElementById("in-sleep").value,
    notes: document.getElementById("in-notes").value,
    mindset_win: document.getElementById("in-mindset").value,
  };
  await postCheckinUpdate(payload, `✅ Saved ${STATE.date} to Win the Day & Check-In Sheet!`);
}

async function quickAddSteps(addCount) {
  const curr = (STATE.overview && STATE.overview.checkin && STATE.overview.checkin.steps) || 0;
  await postCheckinUpdate({ steps: curr + addCount }, `👟 Added +${addCount.toLocaleString()} steps!`);
}

async function quickAddWater(litres) {
  await postCheckinUpdate({ water_add_l: litres }, `💧 Added +${Math.round(litres * 1000)}ml water!`);
}

async function toggleHabit(field) {
  const curr = (STATE.overview && STATE.overview.checkin && STATE.overview.checkin[field]) ? 1 : 0;
  const payload = {};
  payload[field] = curr ? 0 : 1;
  await postCheckinUpdate(payload, "✅ Updated daily checkpoint!");
}

async function quickAddSelectedStaple() {
  const sel = document.getElementById("quick-staple-select");
  if (!sel || !sel.value) return;
  await postCheckinUpdate({ add_staple_id: parseInt(sel.value, 10) }, "🍽️ Staple meal added to today's macros!");
}

async function onSelectCsClass(classId) {
  if (!classId) return;
  await postCheckinUpdate({ cs_class: classId }, "🏋️ Mapped CS Fitness class to Check-In Type!");
}

async function logQuickClassOrStrength() {
  const sel = document.getElementById("act-quick-preset");
  const notesEl = document.getElementById("act-quick-notes");
  if (!sel || !sel.value) return;
  const [category, source, title, dur] = sel.value.split("|");
  await fetch("/api/challenge/activities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      date: STATE.date,
      category,
      source,
      activity_type: category === "GYM" ? "strength" : "class",
      title,
      duration_mins: parseFloat(dur || "45"),
      notes: notesEl ? notesEl.value : "",
    }),
  });
  if (notesEl) notesEl.value = "";
  await loadOverview(STATE.date);
  showToast(`🏋️ Added ${title} to ${STATE.date}!`);
}

async function logGarminRunDetails() {
  const title = (document.getElementById("run-title").value || "").trim() || "Garmin Outdoor Run";
  const distKm = parseFloat(document.getElementById("run-dist-km").value || "0");
  const durMins = parseFloat(document.getElementById("run-dur-mins").value || "0");
  const avgHr = parseInt(document.getElementById("run-avg-hr").value || "0", 10) || null;
  const cals = parseInt(document.getElementById("run-cals").value || "0", 10) || null;
  const steps = parseInt(document.getElementById("run-steps").value || "0", 10) || null;
  await fetch("/api/challenge/activities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      date: STATE.date,
      source: "Garmin Connect",
      activity_type: "running",
      category: "CARDIO",
      title,
      distance_km: distKm > 0 ? distKm : null,
      duration_mins: durMins,
      avg_hr: avgHr,
      calories: cals,
      steps,
      add_steps_to_daily: Boolean(steps && steps > 0),
    }),
  });
  ["run-title", "run-dist-km", "run-dur-mins", "run-avg-hr", "run-cals", "run-steps"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  await loadOverview(STATE.date);
  showToast(`🏃 Logged ${title}${distKm ? " (" + distKm + " km)" : ""} to ${STATE.date}!`);
}

async function triggerLiveSync() {
  const emailEl = document.getElementById("cfg-garmin-email");
  const passEl = document.getElementById("cfg-garmin-pass");
  const mfpEl = document.getElementById("cfg-mfp-user");
  const res = await fetch("/api/challenge/sync/live", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      date: STATE.date,
      garmin_email: emailEl ? emailEl.value : "",
      garmin_password: passEl ? passEl.value : "",
      mfp_username: mfpEl ? mfpEl.value : "",
    }),
  });
  const data = await res.json();
  await loadOverview(STATE.date);
  const msg = (data.messages && data.messages.join(" · ")) || "Sync completed";
  showToast(data.ok ? `🔄 ${msg}` : `ℹ️ ${msg}`);
}

async function triggerSimulateSync() {
  const res = await fetch("/api/challenge/sync/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date: STATE.date }),
  });
  await res.json();
  await loadOverview(STATE.date);
  showToast("⚡ Synced Garmin Connect (Steps, Sleep, Scale, Activity) + MyFitnessPal!");
}

function copyWhatsAppCaption() {
  const box = document.getElementById("wa-caption-box");
  if (!box) return;
  navigator.clipboard.writeText(box.value);
  showToast("📋 Copied WhatsApp #hashtag summary to clipboard!");
}

function downloadDailySummaryPng() {
  const canvas = document.createElement("canvas");
  canvas.width = 800;
  canvas.height = 460;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#060807";
  ctx.fillRect(0, 0, 800, 460);
  ctx.strokeStyle = "#3DFF4F";
  ctx.lineWidth = 6;
  ctx.strokeRect(12, 12, 776, 436);

  const c = (STATE.overview && STATE.overview.checkin) || {};
  const p = (STATE.overview && STATE.overview.profile) || {};
  const wk = (STATE.overview && STATE.overview.week_info) || {};

  ctx.fillStyle = "#3DFF4F";
  ctx.font = "italic bold 32px sans-serif";
  ctx.fillText("CS FITNESS · 8-WEEK CHALLENGE", 38, 62);
  ctx.fillStyle = "#F3F6F4";
  ctx.font = "bold 20px sans-serif";
  ctx.fillText(`${p.client_name || "Ewan t"} · ${STATE.date} (${wk.phase || "Week 1"})`, 38, 96);

  const boxes = [
    ["STEPS", `${(c.steps || 0).toLocaleString()} / ${(wk.step_target || 10000).toLocaleString()}`],
    ["PROTEIN", `${c.protein_g || 0}g / ${p.target_protein_g || 150}g`],
    ["CALORIES", `${(c.calories || 0).toLocaleString()} / ${p.target_calories || 2173}`],
    ["WATER", `${Number(c.water_l || 0).toFixed(2)}L / ${p.target_water_l || 3.66}L`],
    ["TRAINING", `${c.training_type || "REST"}`],
    ["SLEEP", `${c.sleep_str || "8hrs 00m"}`],
  ];
  boxes.forEach((b, idx) => {
    const col = idx % 3;
    const row = Math.floor(idx / 3);
    const x = 38 + col * 245;
    const y = 125 + row * 115;
    ctx.fillStyle = "#121915";
    ctx.fillRect(x, y, 228, 95);
    ctx.fillStyle = "#8A9990";
    ctx.font = "bold 13px sans-serif";
    ctx.fillText(b[0], x + 16, y + 30);
    ctx.fillStyle = "#3DFF4F";
    ctx.font = "bold 22px sans-serif";
    ctx.fillText(b[1], x + 16, y + 68);
  });

  ctx.fillStyle = "#3DFF4F";
  ctx.font = "bold 18px sans-serif";
  ctx.fillText("#Ewan #steps #macros #dinner #snack #winTheDay", 38, 405);

  const link = document.createElement("a");
  link.download = `cs-fitness-${STATE.date}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
  showToast("🖼️ Downloaded End-of-Day Card PNG!");
}

/* ── TAB 2: WORKOUTS ────────────────────────────────────────── */
async function loadWorkouts() {
  const track = document.getElementById("wo-track-select").value || "mens";
  const res = await fetch(`/api/challenge/workouts?track=${encodeURIComponent(track)}`);
  STATE.workoutsData = await res.json();
  const numSel = document.getElementById("wo-num-select");
  if (numSel) {
    const currentVal = numSel.value || "1";
    numSel.innerHTML = "";
    (STATE.workoutsData.workouts || []).forEach((w) => {
      const opt = document.createElement("option");
      opt.value = w.workout_num;
      opt.textContent = w.title;
      numSel.appendChild(opt);
    });
    numSel.value = currentVal;
  }
  renderActiveWorkout();
}

function renderActiveWorkout() {
  if (!STATE.workoutsData) return;
  const wNum = parseInt(document.getElementById("wo-num-select").value || "1", 10);
  const activeWk = parseInt(document.getElementById("wo-week-select").value || "1", 10);
  const workout = (STATE.workoutsData.workouts || []).find((w) => w.workout_num === wNum);
  if (!workout) return;

  document.getElementById("wo-rep-note").textContent = workout.rep_note || "";
  const tbody = document.getElementById("workout-tbody");
  tbody.innerHTML = "";

  workout.rows.forEach((row) => {
    const tr = document.createElement("tr");
    const currVal = (row.weeks && row.weeks[String(activeWk)]) || "";
    const histBadges = [1, 2, 3, 4, 5, 6, 7, 8]
      .filter((wk) => row.weeks && row.weeks[String(wk)])
      .map((wk) => `<span class="badge ${wk === activeWk ? "badge-green" : ""}">W${wk}: ${row.weeks[String(wk)]}</span>`)
      .join(" ");

    tr.innerHTML = `
      <td><span class="badge badge-green">${row.order}</span></td>
      <td style="white-space:normal;min-width:210px">
        <div style="font-weight:700;color:#fff">${row.exercise}</div>
        <div style="font-size:0.71rem;color:var(--muted)">${row.notes || ""}</div>
      </td>
      <td><strong>${row.sets}</strong></td>
      <td><span class="badge">${row.reps}</span></td>
      <td>
        <button class="btn btn-sm" onclick="startRestTimer(${row.rest})">⏱️ ${row.rest}s</button>
      </td>
      <td>
        <div style="display:flex;gap:0.35rem;min-width:215px">
          <input type="text" id="wlog-${row.row_key}" value="${currVal}" placeholder="${row.example || "e.g. 60kg x8"}" />
          <button class="btn btn-green btn-sm" onclick="saveWorkoutRow('${row.row_key}', '${row.order}', '${row.exercise.replace(/'/g, "")}', ${row.sets}, '${row.reps}')">Save</button>
          ${currVal ? `<button class="btn btn-sm" style="background:rgba(248,113,113,0.14);color:#f87171;border:1px solid rgba(248,113,113,0.4);padding:0.25rem 0.45rem" onclick="clearWorkoutRow('${row.row_key}', '${row.order}', '${row.exercise.replace(/'/g, "")}', ${row.sets}, '${row.reps}')" title="Delete / clear logged set">🗑️</button>` : ""}
        </div>
      </td>
      <td style="white-space:normal;min-width:180px">${histBadges || '<span style="color:var(--muted);font-size:0.72rem">No sets logged yet</span>'}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function saveWorkoutRow(rowKey, order, exercise, sets, reps) {
  const track = document.getElementById("wo-track-select").value || "mens";
  const workout_num = parseInt(document.getElementById("wo-num-select").value || "1", 10);
  const week_num = parseInt(document.getElementById("wo-week-select").value || "1", 10);
  const input = document.getElementById(`wlog-${rowKey}`);
  const weight_reps = input ? input.value : "";

  await fetch("/api/challenge/workouts/log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      track,
      workout_num,
      week_num,
      row_key: rowKey,
      exercise_order: order,
      exercise_name: exercise,
      target_sets: sets,
      target_reps: reps,
      weight_reps,
      logged_date: STATE.date,
      mark_checkin_gym: true,
    }),
  });
  await loadWorkouts();
  await loadOverview(STATE.date);
  showToast(weight_reps ? `🏋️ Logged ${exercise} (${weight_reps}) & marked GYM!` : `🗑️ Cleared ${exercise}`);
}

async function clearWorkoutRow(rowKey, order, exercise, sets, reps) {
  const input = document.getElementById(`wlog-${rowKey}`);
  if (input) input.value = "";
  await saveWorkoutRow(rowKey, order, exercise, sets, reps);
}
window.clearWorkoutRow = clearWorkoutRow;

async function markTodayWorkoutComplete() {
  const numSel = document.getElementById("wo-num-select");
  const title = numSel && numSel.options[numSel.selectedIndex] ? numSel.options[numSel.selectedIndex].text : "Men's Workout";
  await postCheckinUpdate({ training_type: "GYM", class_attended: title }, `✅ Logged ${title} on today's check-in!`);
}

function startRestTimer(seconds) {
  clearInterval(STATE.restTimerId);
  STATE.restSecondsLeft = seconds;
  const disp = document.getElementById("rest-timer-display");
  const tick = () => {
    if (STATE.restSecondsLeft <= 0) {
      clearInterval(STATE.restTimerId);
      if (disp) disp.textContent = "🔔 REST COMPLETE — GO!";
      showToast("🔔 Rest timer complete — next working set!");
      return;
    }
    if (disp) disp.textContent = `⏱️ Rest: ${STATE.restSecondsLeft}s`;
    STATE.restSecondsLeft -= 1;
  };
  tick();
  STATE.restTimerId = setInterval(tick, 1000);
}

/* ── TAB 3: WEEKLY CHECK-IN SHEET + TELEGRAM + PHOTOS ──────── */
async function loadWeekSheet(weekNum) {
  const res = await fetch(`/api/challenge/week/${encodeURIComponent(weekNum)}`);
  const sheet = await res.json();
  renderWeekSheetData(sheet);
}

function renderWeekSheetData(sheet) {
  if (!sheet) return;
  const weekNum = sheet.week_num;
  const avg = sheet.averages || {};

  const schedBanner = document.getElementById("ci-checkin-schedule-banner");
  if (schedBanner) {
    if (Number(weekNum) === 1) {
      schedBanner.style.background = "rgba(56,189,248,0.10)";
      schedBanner.style.borderColor = "rgba(56,189,248,0.4)";
      schedBanner.innerHTML = `📅 <strong>Week 1 Friday Check-In (${sheet.checkin_date || ""}):</strong> Log your Friday weigh-in &amp; submit your weekly review. <strong>🚫 No photos required this Friday</strong> (starting photos were sent on Day 1 Monday).`;
    } else if (Number(weekNum) === 0) {
      schedBanner.style.background = "rgba(61,255,79,0.09)";
      schedBanner.style.borderColor = "rgba(61,255,79,0.35)";
      schedBanner.innerHTML = `📸 <strong>Start Check-In · Day 1 Monday (${sheet.checkin_date || ""}):</strong> Submit your <strong>Starting Weight, Measurements &amp; 3 Starting Photos</strong> (Front · Side · Back) on Monday Day 1.`;
    } else {
      schedBanner.style.background = "rgba(61,255,79,0.09)";
      schedBanner.style.borderColor = "rgba(61,255,79,0.35)";
      schedBanner.innerHTML = `📸 <strong>Week ${weekNum} Friday Check-In (${sheet.checkin_date || ""}):</strong> Log your Friday weigh-in, weekly review &amp; <strong>3 Friday Progress Photos</strong> (Front · Side · Back).`;
    }
  }

  document.getElementById("ci-avg-cals").textContent = `${Math.round(avg.avg_calories || 0).toLocaleString()} kcal`;
  document.getElementById("ci-avg-prot").textContent = `Avg Protein: ${Math.round(avg.avg_protein_g || 0)}g / 150g`;
  document.getElementById("ci-avg-steps").textContent = Math.round(avg.avg_steps || 0).toLocaleString();
  document.getElementById("ci-step-min-label").textContent = `Week Min: ${(sheet.step_target || 10000).toLocaleString()} / day`;
  document.getElementById("ci-avg-weight").textContent = `${Number(avg.avg_weight_kg || 0).toFixed(2)} kg (Target: ${sheet.target_weight_kg} kg)`;
  document.getElementById("ci-weight-loss-pct").textContent = `Change: ${Number(avg.weight_loss_pct || 0).toFixed(2)}% · ${avg.days_on_plan || 0}/${avg.days_logged || 0} days green`;

  const tbody = document.getElementById("checkin-sheet-tbody");
  tbody.innerHTML = "";
  (sheet.rows || []).forEach((r) => {
    const tr = document.createElement("tr");
    const isActive = r.date === STATE.date;
    if (isActive) {
      tr.style.background = "rgba(61, 255, 79, 0.08)";
    } else if (r.is_friday_checkin || r.is_start_checkin_day) {
      tr.style.background = "rgba(56, 189, 248, 0.05)";
    }
    const todayIso = getTodayIsoDate();
    const yestIso = getOffsetIsoDate(todayIso, -1);
    const dayTag =
      r.date === todayIso
        ? ' <span class="badge badge-green">TODAY</span>'
        : r.date === yestIso
        ? ' <span class="badge badge-blue">YESTERDAY</span>'
        : "";
    let checkinBadge = "";
    if (r.is_start_checkin_day) {
      checkinBadge = ' <span class="badge badge-green" style="font-size:0.62rem">📸 START CHECK-IN (MON)</span>';
    } else if (r.is_friday_checkin && Number(weekNum) === 1) {
      checkinBadge = ' <span class="badge badge-blue" style="font-size:0.62rem">📅 FRI CHECK-IN (NO PHOTOS)</span>';
    } else if (r.is_friday_checkin && Number(weekNum) >= 2) {
      checkinBadge = ' <span class="badge badge-green" style="font-size:0.62rem">📸 FRI CHECK-IN (+3 PHOTOS)</span>';
    }
    const stepClass = r.steps > 0 ? (r.step_green ? "cell-green" : "cell-red") : "";
    const protClass = r.protein_g > 0 ? (r.protein_green ? "cell-green" : "cell-red") : "";
    const calClass = r.calories > 0 ? (r.calories_green ? "cell-green" : "cell-red") : "";
    const planClass = r.stick_to_plan === "Y" ? "cell-green" : r.stick_to_plan === "N" ? "cell-red" : "";

    tr.innerHTML = `
      <td>
        <a href="#today" onclick="jumpToDate('${r.date}');return false;" style="color:var(--green);text-decoration:none;font-weight:700">${r.date}</a>${dayTag}${checkinBadge}
      </td>
      <td><strong>${r.day_initial}</strong> (${r.day_short})</td>
      <td><input type="number" step="0.1" id="ci-w-${r.date}" value="${r.weight_kg != null ? r.weight_kg : ""}" placeholder="kg" style="width:68px;padding:0.25rem 0.35rem;font-size:0.76rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td><input type="time" id="ci-t-${r.date}" value="${r.weigh_time || "06:30"}" style="width:78px;padding:0.25rem 0.3rem;font-size:0.74rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td>
        <select id="ci-type-${r.date}" style="width:105px;padding:0.25rem 0.3rem;font-size:0.74rem" onchange="saveSheetRow('${r.date}')">
          <option value="GYM" ${r.training_type === "GYM" ? "selected" : ""}>GYM</option>
          <option value="CARDIO" ${r.training_type === "CARDIO" ? "selected" : ""}>CARDIO</option>
          <option value="GYM & CARDIO" ${r.training_type === "GYM & CARDIO" ? "selected" : ""}>GYM &amp; CARDIO</option>
          <option value="REST" ${(!r.training_type || r.training_type === "REST") ? "selected" : ""}>REST</option>
        </select>
      </td>
      <td class="${stepClass}"><input type="number" id="ci-steps-${r.date}" value="${r.steps || 0}" style="width:76px;padding:0.25rem 0.35rem;font-size:0.76rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td class="${protClass}"><input type="number" id="ci-prot-${r.date}" value="${r.protein_g || 0}" style="width:62px;padding:0.25rem 0.35rem;font-size:0.76rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td class="${calClass}"><input type="number" id="ci-cals-${r.date}" value="${r.calories || 0}" style="width:68px;padding:0.25rem 0.35rem;font-size:0.76rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td><input type="text" id="ci-sleep-${r.date}" value="${r.sleep_str || ""}" placeholder="8hrs 00m" style="width:92px;padding:0.25rem 0.35rem;font-size:0.74rem" onchange="saveSheetRow('${r.date}')" /></td>
      <td class="${planClass}">
        <select id="ci-plan-${r.date}" style="width:54px;padding:0.25rem;font-size:0.74rem" onchange="saveSheetRow('${r.date}')">
          <option value="Y" ${r.stick_to_plan !== "N" ? "selected" : ""}>Y</option>
          <option value="N" ${r.stick_to_plan === "N" ? "selected" : ""}>N</option>
        </select>
      </td>
      <td style="min-width:170px">
        <input type="text" id="ci-notes-${r.date}" value="${(r.notes || "").replace(/"/g, "&quot;")}" placeholder="Notes..." style="width:100%;padding:0.25rem 0.4rem;font-size:0.73rem" onchange="saveSheetRow('${r.date}')" />
      </td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById("tg-summary-box").value = sheet.telegram_summary || "";
  document.getElementById("tg-direct-link").href = sheet.telegram_deep_link || "https://t.me/";

  // Render 8-Week Target Strip
  const strip = document.getElementById("wk8-targets-strip");
  if (strip && STATE.overview && STATE.overview.profile) {
    strip.innerHTML = (STATE.overview.profile.weekly_targets || [])
      .map(
        (wt) => `
        <div style="background:var(--surface-2);border:1px solid ${wt.week === Number(weekNum) ? "var(--green)" : "var(--border)"};border-radius:8px;padding:0.45rem;text-align:center">
          <div style="font-size:0.65rem;color:var(--muted)">WK ${wt.week} (${wt.start_date.slice(5)})</div>
          <div style="font-size:0.88rem;font-weight:800;color:#fff">${Number(wt.target_weight_kg).toFixed(2)} kg</div>
          <div style="font-size:0.68rem;color:var(--green)">${wt.min_steps.toLocaleString()} steps</div>
        </div>`
      )
      .join("");
  }

  renderPhotosVault((STATE.overview && STATE.overview.progress_photos) || []);
}

async function saveSheetRow(dateStr) {
  const wVal = document.getElementById(`ci-w-${dateStr}`).value;
  const payload = {
    date: dateStr,
    weight_kg: wVal !== "" ? parseFloat(wVal) : null,
    weigh_time: document.getElementById(`ci-t-${dateStr}`).value,
    training_type: document.getElementById(`ci-type-${dateStr}`).value,
    steps: parseInt(document.getElementById(`ci-steps-${dateStr}`).value || "0", 10),
    protein_g: parseInt(document.getElementById(`ci-prot-${dateStr}`).value || "0", 10),
    calories: parseInt(document.getElementById(`ci-cals-${dateStr}`).value || "0", 10),
    sleep: document.getElementById(`ci-sleep-${dateStr}`).value,
    stick_to_plan: document.getElementById(`ci-plan-${dateStr}`).value,
    notes: document.getElementById(`ci-notes-${dateStr}`).value,
  };
  await fetch("/api/challenge/checkins", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const sel = document.getElementById("ci-week-select");
  await loadWeekSheet(sel ? sel.value : "0");
  if (dateStr === STATE.date) {
    await loadOverview(STATE.date);
  }
  showToast(`✅ Updated ${dateStr} on Check-In Sheet!`);
}

function jumpToDate(dateStr) {
  document.getElementById("active-date").value = dateStr;
  switchTab("today");
  loadOverview(dateStr);
}

function copyTelegramSummary() {
  const box = document.getElementById("tg-summary-box");
  if (!box) return;
  navigator.clipboard.writeText(box.value);
  showToast("📋 Copied Weekly Check-In Telegram summary!");
}

async function sendWeeklyTelegram() {
  const week_num = parseInt(document.getElementById("ci-week-select").value || "1", 10);
  const custom_message = document.getElementById("tg-summary-box").value;
  const res = await fetch("/api/challenge/telegram/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ week_num, custom_message }),
  });
  const data = await res.json();
  if (data.sent_via_api) {
    showToast("✈️ Sent Weekly Check-In directly via Telegram Bot API!");
  } else {
    navigator.clipboard.writeText(custom_message);
    showToast("✈️ Copied summary & prepared Telegram link for Chris!");
  }
}

function renderPhotosVault(photos) {
  const el = document.getElementById("photos-vault-list");
  if (!el) return;
  el.innerHTML = photos
    .map(
      (ph) => `
      <div class="habit-item done" style="cursor:default">
        <div>
          <strong>Week ${ph.week_num} · ${ph.pose} Pose</strong>
          <div style="font-size:0.7rem;color:var(--muted)">${ph.taken_date} · ${ph.weight_kg || 84}kg · ${ph.fasted_confirmed ? "Fasted ✅" : ""}</div>
        </div>
        <span class="badge badge-green">Baseline Logged</span>
      </div>`
    )
    .join("");
}

async function addProgressPhoto() {
  const week_num = parseInt(document.getElementById("ph-week").value || "1", 10);
  const pose = document.getElementById("ph-pose").value || "Front";
  const weight_kg = parseFloat(document.getElementById("ph-weight").value || "84.0");
  const res = await fetch("/api/challenge/photos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ week_num, pose, weight_kg, taken_date: STATE.date, fasted_confirmed: true }),
  });
  const photos = await res.json();
  if (STATE.overview) STATE.overview.progress_photos = photos;
  renderPhotosVault(photos);
  showToast(`📸 Logged Week ${week_num} ${pose} progress photo!`);
}

/* ── TAB 4: INTEGRATIONS, STAPLES, ROUTES & RHYTHM ─────────── */
function renderIntegrationsAndStaples(data) {
  const integ = data.integrations || {};
  document.getElementById("cfg-garmin-email").value = integ.garmin_email || "";
  document.getElementById("cfg-nutri-provider").value = integ.nutrition_provider || "myfitnesspal";
  document.getElementById("cfg-mfp-user").value = integ.mfp_username || "ewantaylor";
  document.getElementById("cfg-tg-token").value = integ.telegram_bot_token || "";
  document.getElementById("cfg-tg-chat").value = integ.telegram_chat_id || integ.coach_telegram_handle || "csfitness_chris";

  // Rhythm tasks
  const rEl = document.getElementById("rhythm-tasks-list");
  if (rEl) {
    rEl.innerHTML = (data.weekly_rhythm || [])
      .map(
        (t) => `
        <div class="habit-item ${t.completed ? "done" : ""}" onclick="toggleRhythmTask(${t.id})">
          <div>
            <div style="font-size:0.78rem;font-weight:700;color:#fff">[${t.day_name}] ${t.title}</div>
            <div style="font-size:0.7rem;color:var(--muted)">${t.description}</div>
          </div>
          <span class="badge ${t.completed ? "badge-green" : ""}">${t.completed ? "Done ✅" : t.category}</span>
        </div>`
      )
      .join("");
  }

  // Staples library
  const sEl = document.getElementById("staples-library-list");
  if (sEl) {
    sEl.innerHTML = (data.staple_meals || [])
      .map(
        (m) => `
        <div class="habit-item" style="cursor:default">
          <div>
            <div style="font-size:0.77rem;font-weight:700;color:#fff"><span class="badge badge-green">${m.slot}</span> ${m.name}</div>
            <div style="font-size:0.7rem;color:var(--muted);margin-top:0.15rem">${m.calories} kcal · <strong>${m.protein_g}g P</strong> · ${m.carbs_g}g C · ${m.fats_g}g F · ${m.fibre_g}g Fibre</div>
          </div>
          <button class="btn btn-green btn-sm" onclick="postCheckinUpdate({add_staple_id:${m.id}}, '🍽️ Added ${m.name.replace(/'/g, "")}!')">+ Add</button>
        </div>`
      )
      .join("");
  }

  // Step Routes
  const rtEl = document.getElementById("routes-library-list");
  if (rtEl) {
    rtEl.innerHTML = (data.step_routes || [])
      .map(
        (rt) => `
        <div class="habit-item" style="cursor:default">
          <div>
            <div style="font-size:0.78rem;font-weight:700;color:#fff">👟 ${rt.name} (${rt.duration_mins} mins)</div>
            <div style="font-size:0.7rem;color:var(--muted)">${rt.notes}</div>
          </div>
          <button class="btn btn-green btn-sm" onclick="postCheckinUpdate({add_route_id:${rt.id}}, '👟 Banked ${rt.est_steps.toLocaleString()} steps!')">+${rt.est_steps.toLocaleString()} steps</button>
        </div>`
      )
      .join("");
  }

  // CS Fitness Timetable
  const ttEl = document.getElementById("timetable-list");
  if (ttEl) {
    ttEl.innerHTML = (data.cs_timetable || [])
      .map(
        (c) => `
        <div class="habit-item" onclick="onSelectCsClass('${c.id}')">
          <div>
            <div style="font-size:0.76rem;font-weight:700;color:#fff">${c.name}</div>
            <div style="font-size:0.68rem;color:var(--muted)">${c.category} · ${c.note}</div>
          </div>
          <span class="badge badge-green">→ ${c.training_type}</span>
        </div>`
      )
      .join("");
  }
}

async function saveIntegrationsConfig() {
  const payload = {
    garmin_email: document.getElementById("cfg-garmin-email").value,
    garmin_password: document.getElementById("cfg-garmin-pass").value,
    nutrition_provider: document.getElementById("cfg-nutri-provider").value,
    mfp_username: document.getElementById("cfg-mfp-user").value,
    telegram_bot_token: document.getElementById("cfg-tg-token").value,
    telegram_chat_id: document.getElementById("cfg-tg-chat").value,
  };
  await fetch("/api/challenge/integrations", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadOverview(STATE.date);
  showToast("💾 Saved Garmin, MyFitnessPal & Telegram configuration!");
}

async function testTelegramBotCommand(cmd) {
  const res = await fetch("/api/challenge/telegram/webhook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: cmd, date: STATE.date }),
  });
  const data = await res.json();
  const replyEl = document.getElementById("bot-command-reply");
  if (replyEl) replyEl.textContent = data.reply || "";
  await loadOverview(STATE.date);
  showToast(`🤖 Executed Telegram command: ${cmd}`);
}

async function toggleRhythmTask(taskId) {
  await fetch(`/api/challenge/rhythm/${taskId}/toggle`, { method: "POST" });
  await loadOverview(STATE.date);
  showToast("🗓️ Updated Weekly Rhythm task!");
}

/* ── TAB 5: COACH PORTAL (CALCULATOR, COHORT & WHATSAPP) ───── */
async function runCoachCalculator(saveProfile) {
  const payload = {
    client_name: document.getElementById("calc-name").value || "New Challenger",
    start_weight_kg: parseFloat(document.getElementById("calc-sw").value || "84.0"),
    target_weight_kg: parseFloat(document.getElementById("calc-tw").value || "78.3"),
    start_body_fat_pct: parseFloat(document.getElementById("calc-sbf").value || "16.0"),
    target_body_fat_pct: parseFloat(document.getElementById("calc-tbf").value || "14.0"),
    protein_g: parseInt(document.getElementById("calc-prot").value || "150", 10),
    returning_member: document.getElementById("calc-returning").checked,
    save_profile: Boolean(saveProfile),
  };
  const res = await fetch("/api/challenge/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const c = await res.json();
  const out = document.getElementById("calc-output-box");
  if (out) {
    out.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.45rem;margin-bottom:0.55rem">
        <div><span style="color:var(--muted);font-size:0.68rem">LEAN BODY MASS</span><br/><strong>${c.lean_body_mass_kg} kg</strong></div>
        <div><span style="color:var(--muted);font-size:0.68rem">FAT MASS / TO LOSE</span><br/><strong>${c.fat_mass_kg} kg (${c.to_lose_kg} kg)</strong></div>
        <div><span style="color:var(--muted);font-size:0.68rem">DAILY CALORIES</span><br/><strong style="color:var(--green)">${c.target_calories.toLocaleString()} kcal</strong></div>
        <div><span style="color:var(--muted);font-size:0.68rem">WATER INTAKE</span><br/><strong style="color:var(--blue)">${c.target_water_l} L/day</strong></div>
      </div>
      <div style="font-size:0.75rem;margin-bottom:0.45rem">
        Macros: <strong>${c.target_protein_g}g Protein</strong> (${c.protein_kcal} kcal) ·
        <strong>${c.target_fats_g}g Fats</strong> ·
        <strong>${c.target_carbs_g}g Carbs</strong> ·
        <strong>30g Fibre</strong>
      </div>
      <div style="font-size:0.71rem;color:var(--muted)">
        Wk 1→8 Weight Curve: ${c.weekly_targets.map((w) => `W${w.week}: ${w.target_weight_kg}kg (${w.min_steps / 1000}k)`).join(" · ")}
      </div>
    `;
  }
  if (saveProfile) {
    await loadCohortBoard();
    showToast(`➕ Saved ${payload.client_name} to 19 Oct Cohort!`);
  }
}

async function loadCohortBoard() {
  const res = await fetch("/api/challenge/coach/cohort");
  const data = await res.json();
  document.getElementById("cohort-count-badge").textContent = `${data.challenger_count} Challengers Active`;
  const tbody = document.getElementById("cohort-tbody");
  tbody.innerHTML = (data.challengers || [])
    .map(
      (c) => `
      <tr>
        <td><strong style="color:#fff">${c.client_name}</strong> ${c.returning_member ? '<span class="badge badge-blue">Returning</span>' : ""}</td>
        <td>${c.goal}</td>
        <td>${c.start_weight_kg} kg (${c.start_body_fat_pct}% BF)</td>
        <td style="color:var(--green);font-weight:700">${c.target_weight_kg} kg (${c.to_lose_kg} kg)</td>
        <td>${c.lean_body_mass_kg} kg LBM / ${c.fat_mass_kg} kg Fat</td>
        <td><strong>${c.target_calories.toLocaleString()} kcal</strong></td>
        <td>${c.target_protein_g}g P / ${c.target_fats_g}g F / ${c.target_carbs_g}g C</td>
        <td style="color:var(--blue)">${c.target_water_l} L</td>
        <td>${c.returning_member ? "14,000 → 17,000" : "10,000 → 17,000"}</td>
      </tr>`
    )
    .join("");
}

async function loadWhatsAppFeed() {
  const res = await fetch("/api/challenge/whatsapp/feed");
  const data = await res.json();
  const container = document.getElementById("wa-feed-container");
  if (!container) return;
  container.innerHTML = (data.posts || [])
    .map(
      (p) => `
      <div class="habit-item ${p.role === "coach" ? "done" : ""}" style="cursor:default;align-items:flex-start">
        <div style="flex:1">
          <div style="display:flex;justify-content:space-between;gap:0.4rem">
            <strong style="color:${p.role === "coach" ? "var(--green)" : "#fff"};font-size:0.76rem">${p.sender}</strong>
            <span style="font-size:0.66rem;color:var(--muted)">${p.posted_at}</span>
          </div>
          <div style="font-size:0.73rem;color:var(--text);margin-top:0.2rem">${p.message}</div>
          <div style="margin-top:0.25rem">${(p.hashtags || []).map((h) => `<span class="badge badge-green" style="margin-right:0.25rem">${h}</span>`).join("")}</div>
        </div>
      </div>`
    )
    .join("");
}

async function uploadWhatsAppExport() {
  const fileIn = document.getElementById("wa-import-file");
  if (!fileIn || !fileIn.files || !fileIn.files[0]) {
    showToast("Select a WhatsApp .zip or _chat.txt file first!");
    return;
  }
  const fd = new FormData();
  fd.append("file", fileIn.files[0]);
  const res = await fetch("/api/challenge/whatsapp/import", {
    method: "POST",
    body: fd,
  });
  const data = await res.json();
  await loadWhatsAppFeed();
  showToast(`📥 Imported ${data.extracted_count} coaching & #hashtag posts from WhatsApp!`);
}

document.addEventListener("DOMContentLoaded", () => {
  const dateInput = document.getElementById("active-date");
  if (dateInput) {
    dateInput.value = STATE.date;
    dateInput.addEventListener("change", () => loadOverview(dateInput.value));
  }
  loadOverview(STATE.date);
});


