// CS Fitness 8-Week Challenge — Real Data, Week-over-Week Progress, 3-Photo Weekly Check-In & Workout Roll-Up
window.PROGRESS_SUMMARY = null;

function getActiveSheetWeek() {
  const sel = document.getElementById('ci-week-select');
  return sel ? parseInt(sel.value || '0', 10) : 0;
}

async function initRealDataAndProgress() {
  injectDataSourceClarifiers();
  injectWorkoutRollupBanner();
  injectWeekOverWeekOnCheckinTab();
  upgradeThreePhotoWeeklyVault();
  upgradeIntegrationsSaveAndImport();
  await ensureServerRehydratedFromBrowserVault();
  if (typeof STATE !== 'undefined' && STATE && STATE.overview) {
    window.renderTodayDashboard(STATE.overview);
    if (STATE.overview.current_week_sheet) {
      window.renderWeekSheetData(STATE.overview.current_week_sheet);
    }
  }
  renderThreePhotoSlots();
  renderDataSourceBadges();
  renderSavedIntegrationStatus();
  await refreshProgressSummary();
  await pullServerBackupIntoBrowserVault();
}

async function refreshProgressSummary() {
  try {
    const res = await fetch('/api/challenge/progress/summary');
    const data = await res.json();
    if (data.ok) {
      window.PROGRESS_SUMMARY = data;
      renderWeekOverWeekTable();
      renderWorkoutRollupBanner();
      renderThreePhotoSlots();
      renderWeeklySubmissionState();
      renderWeeklyCheckinCardCanvas();
      renderCoachWowSideBySide();
      renderCoachCheckinInbox();
      renderDailyJourneyMoments();
      renderDataSourceBadges();
      renderSavedIntegrationStatus();
      loadCohortBlocks();
    }
  } catch (e) {
    console.warn('Progress summary fetch error:', e);
  }
}

const DEMO_GARMIN_SOURCES = [
  'Garmin Fenix 7',
  'Garmin Connect (Fenix 7 + Index S2)',
  'Garmin Connect (Simulated)',
];

function isDemoCheckin(c) {
  return Boolean(c && DEMO_GARMIN_SOURCES.includes(c.sync_source_garmin));
}

function isDemoActivity(a) {
  const gid = String((a && a.garmin_activity_id) || '');
  return gid.startsWith('act-101') || gid.startsWith('garmin-run-') || gid.startsWith('garmin-gym-');
}

function injectDataSourceClarifiers() {
  // Demo data and Clear Demo Data buttons removed — app runs purely on real logged & synced data
  const oldBtn1 = document.getElementById('btn-hdr-clear-demo');
  if (oldBtn1) oldBtn1.remove();
  const oldBtn2 = document.getElementById('btn-clear-demo');
  if (oldBtn2) oldBtn2.remove();
}

async function clearAllFakeDataNow() {
  await fetch('/api/challenge/clear-fake-data', { method: 'POST' });
  await loadOverview(STATE.date);
  await refreshProgressSummary();
  showToast('🧹 Demo data cleared — showing only your real entries!');
}

// Wrap renderTodayDashboard so legacy demo/simulated rows show as 0/clean and null Garmin metrics show "—"
const _origRenderTodayDashboard = window.renderTodayDashboard;
window.renderTodayDashboard = function(data) {
  if (data) {
    data.daily_activities = (data.daily_activities || []).filter((a) => !isDemoActivity(a));
    if (isDemoCheckin(data.checkin)) {
      Object.assign(data.checkin, {
        _was_demo: true,
        weight_kg: null,
        weigh_time: '06:30',
        training_type: 'REST',
        class_attended: '',
        steps: 0,
        protein_g: 0,
        calories: 0,
        carbs_g: 0,
        fats_g: 0,
        fibre_g: 0,
        water_l: 0,
        sleep_mins: 0,
        sleep_str: '',
        sleep_score: null,
        body_battery: null,
        resting_hr: null,
        stick_to_plan: 'Y',
        morning_steps_banked: 0,
        checkpoint_12pm_5k: 0,
        checkpoint_5pm_10k: 0,
        caffeine_cutoff_met: 0,
        electrolytes_taken: 0,
        notes: '',
        mindset_win: '',
        sync_source_garmin: '',
        sync_source_nutrition: '',
      });
      data.win_the_day = { score: 0, checks: {} };
      data.rolling_weight = { current_7d_avg: null, points: [] };
      if (data.whatsapp_share) {
        const handle = ((data.profile && data.profile.client_name) || 'Challenger').split(' ')[0].replace(/[^A-Za-z0-9]/g, '') || 'Challenger';
        data.whatsapp_share.caption = `${data.date || STATE.date} Check-In · 0 steps · 0 kcal · 0g P · 0.0L H2O #${handle} #steps #macros #winTheDay`;
      }
    }
  }
  if (_origRenderTodayDashboard) _origRenderTodayDashboard(data);
  const c = (data && data.checkin) || {};
  const ss = document.getElementById('td-sleep-score');
  const bb = document.getElementById('td-body-battery');
  const rhr = document.getElementById('td-rhr');
  if (ss) ss.textContent = c.sleep_score != null ? `${c.sleep_score}/100` : '—';
  if (bb) bb.textContent = c.body_battery != null ? `${c.body_battery}%` : '—';
  if (rhr) rhr.textContent = c.resting_hr != null ? `${c.resting_hr} bpm` : '—';
  const sleepCardEl = document.getElementById('td-sleep-card-val');
  const sleepBadgeEl = document.getElementById('sleep-status-badge');
  const sleepDisplay = c.sleep_str || (c.sleep_mins > 0 ? `${Math.floor(c.sleep_mins / 60)}h ${c.sleep_mins % 60}m` : '—');
  if (sleepCardEl) sleepCardEl.innerHTML = `${sleepDisplay} <span style="font-size:0.78rem;color:var(--muted)">/ 8h 00m</span>`;
  if (sleepBadgeEl) {
    sleepBadgeEl.textContent = (c.sleep_mins || 0) >= 480 ? '✅ 8h+ Hit' : '8h Target';
    sleepBadgeEl.className = 'badge ' + ((c.sleep_mins || 0) >= 480 ? 'badge-green' : '');
  }
  const scSleep = document.getElementById('sc-sleep');
  const scTrain = document.getElementById('sc-training');
  if (scSleep) scSleep.textContent = sleepDisplay;
  if (scTrain) scTrain.textContent = c.training_type || 'REST';
  renderDailyJourneyMoments();
  renderDataSourceBadges();
};

const _origRenderWeekSheetData = window.renderWeekSheetData;
window.renderWeekSheetData = function(sheet) {
  if (sheet && Array.isArray(sheet.rows)) {
    sheet.rows.forEach((r) => {
      if (isDemoCheckin(r)) {
        Object.assign(r, {
          _was_demo: true,
          weight_kg: null,
          weigh_time: '06:30',
          training_type: 'REST',
          steps: 0,
          protein_g: 0,
          calories: 0,
          sleep_str: '',
          stick_to_plan: 'Y',
          notes: '',
          step_green: false,
          protein_green: false,
          calories_green: false,
          sync_source_garmin: '',
          sync_source_nutrition: '',
        });
      }
    });
    const real = sheet.rows.filter((r) => r.steps > 0 || r.calories > 0 || r.weight_kg != null);
    const wts = real.filter((r) => r.weight_kg != null).map((r) => Number(r.weight_kg));
    sheet.averages = {
      avg_calories: real.length ? Math.round(real.reduce((s, r) => s + (r.calories || 0), 0) / real.length) : 0,
      avg_protein_g: real.length ? Math.round(real.reduce((s, r) => s + (r.protein_g || 0), 0) / real.length) : 0,
      avg_steps: real.length ? Math.round(real.reduce((s, r) => s + (r.steps || 0), 0) / real.length) : 0,
      avg_weight_kg: wts.length ? Number((wts.reduce((a, b) => a + b, 0) / wts.length).toFixed(2)) : 0,
      weight_loss_pct: 0,
      days_logged: real.length,
      days_on_plan: real.filter((r) => r.stick_to_plan === 'Y').length,
    };
  }
  if (_origRenderWeekSheetData) _origRenderWeekSheetData(sheet);
  const wk = getActiveSheetWeek();
  const photos = ((STATE.overview && STATE.overview.progress_photos) || []).filter((p) => Number(p.week_num) === wk);
  const posesLogged = ['Front', 'Side', 'Back'].filter((pose) => photos.some((p) => p.pose === pose));
  const box = document.getElementById('tg-summary-box');
  if (box && !box.value.includes('Progress Photos (')) {
    box.value += `\n📸 Progress Photos (${posesLogged.length}/3 Included): ${posesLogged.join(', ') || 'None recorded yet'}`;
  }
  renderWeekOverWeekTable();
  renderThreePhotoSlots();
  renderWeeklySubmissionState();
};

const _origPostCheckinUpdate = window.postCheckinUpdate;
window.postCheckinUpdate = async function(payload, toastMsg) {
  const c = STATE.overview && STATE.overview.checkin;
  if (c && c._was_demo) {
    payload = Object.assign({
      weight_kg: null,
      steps: 0,
      protein_g: 0,
      calories: 0,
      carbs_g: 0,
      fats_g: 0,
      fibre_g: 0,
      water_l: 0,
      sleep: '',
      morning_steps_banked: 0,
      checkpoint_12pm_5k: 0,
      checkpoint_5pm_10k: 0,
      caffeine_cutoff_met: 0,
      electrolytes_taken: 0,
      notes: '',
      mindset_win: '',
      sync_source_garmin: 'Manual Entry',
      sync_source_nutrition: 'Manual Entry',
    }, payload);
  } else if (!payload.sync_source_garmin) {
    payload.sync_source_garmin = 'Manual Entry';
  }
  if (typeof window.recordCheckinInBrowserVault === 'function') {
    window.recordCheckinInBrowserVault(payload);
  }
  let res;
  if (_origPostCheckinUpdate) {
    res = await _origPostCheckinUpdate(payload, toastMsg);
  }
  if (typeof window.recordCheckinInBrowserVault === 'function' && STATE.overview && STATE.overview.checkin) {
    window.recordCheckinInBrowserVault(STATE.overview.checkin);
  }
  if (typeof window.pullServerBackupIntoBrowserVault === 'function') {
    window.pullServerBackupIntoBrowserVault();
  }
  return res;
};

const _origRenderIntegrations = window.renderIntegrationsAndStaples;
window.renderIntegrationsAndStaples = function(data) {
  if (_origRenderIntegrations) _origRenderIntegrations(data);
  const integ = (data && data.integrations) || {};
  const mfpEl = document.getElementById('cfg-mfp-user');
  if (mfpEl) mfpEl.value = integ.mfp_username || '';
  renderSavedIntegrationStatus();
};

function renderDataSourceBadges() {
  const c = (STATE.overview && STATE.overview.checkin) || {};
  const integ = (STATE.overview && STATE.overview.integrations) || {};
  const gSrc = c.sync_source_garmin || (integ.garmin_email ? `Saved (${integ.garmin_email})` : 'Manual Entry');
  const nSrc = c.calories > 0 ? `Manual Entry (${c.calories} kcal · ${c.protein_g || 0}g P)` : 'Add Manually in Step 2';

  const panelToday = document.getElementById('panel-today');
  let banner = document.getElementById('live-source-explainer');
  if (panelToday && !banner) {
    banner = document.createElement('div');
    banner.id = 'live-source-explainer';
    banner.style.cssText = 'margin-bottom:10px;padding:8px 12px;border-radius:10px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3);font-size:12px;color:#cbd5e1;';
    panelToday.insertBefore(banner, panelToday.firstChild);
  }
  if (banner) {
    const hasData = (c.steps > 0 || c.calories > 0 || c.weight_kg != null || c.sleep_mins > 0);
    banner.innerHTML = hasData
      ? `📊 <strong>${STATE.date} Data Sources:</strong> Steps/Scale/Sleep: <strong>${gSrc}</strong> · Calories/Macros: <strong>${nSrc}</strong>`
      : `✨ <strong>${STATE.date}: Clean Slate (0 mocked metrics).</strong> Enter your numbers below, tap a Staple Meal, or click <strong>🔄 Live Sync</strong> once Garmin/MFP is saved in Tab 4.`;
  }
}

// ── WORKOUT ROLL-UP BANNER & HOOK (TAB 2 -> TAB 1 & TAB 3) ──────────────────
function injectWorkoutRollupBanner() {
  const panel = document.getElementById('panel-workouts');
  if (!panel || document.getElementById('workout-rollup-card')) return;
  const card = document.createElement('div');
  card.id = 'workout-rollup-card';
  card.className = 'card';
  card.style.cssText = 'border:1px solid rgba(61,255,79,0.35);margin-bottom:0.8rem;';
  panel.insertBefore(card, panel.firstChild);
}

function renderWorkoutRollupBanner() {
  const card = document.getElementById('workout-rollup-card');
  if (!card || !window.PROGRESS_SUMMARY) return;
  const wk = parseInt(document.getElementById('wo-week-select')?.value || '1', 10);
  const wNum = parseInt(document.getElementById('wo-num-select')?.value || '1', 10);
  const wkSummary = (PROGRESS_SUMMARY.weeks || []).find(w => w.week_num === wk) || {};
  card.innerHTML = `
    <div class="card-header">
      <div class="card-title">🔗 Where Your Workout Logs Roll Up (Week ${wk})</div>
      <span class="badge badge-green">${wkSummary.workout_exercises_logged || 0} Exercises · ${wkSummary.workout_sets_logged || 0} Sets · ${(wkSummary.workout_volume_kg || 0).toLocaleString()} kg Volume</span>
    </div>
    <div style="font-size:0.75rem;color:var(--muted);line-height:1.45">
      Every set you save below (e.g. <code>60kg x8, 8</code>) automatically rolls up into <strong>3 places</strong>:
      <strong>1) Today Tab (${STATE.date})</strong> under Today's Workouts (Workout ${wNum} sets & kg tonnage) ·
      <strong>2) Weekly Check-In Sheet</strong> (marks Training Type as <code>GYM</code> or <code>GYM & CARDIO</code>) ·
      <strong>3) Week-over-Week Progress Table</strong> (tracks weekly strength sets & volume).
    </div>
  `;
}

const _origSaveWorkoutRow = window.saveWorkoutRow;
window.saveWorkoutRow = async function(rowKey, order, exercise, sets, reps) {
  if (_origSaveWorkoutRow) {
    await _origSaveWorkoutRow(rowKey, order, exercise, sets, reps);
  }
  const track = document.getElementById('wo-track-select')?.value || 'mens';
  const workout_num = parseInt(document.getElementById('wo-num-select')?.value || '1', 10);
  const week_num = parseInt(document.getElementById('wo-week-select')?.value || '1', 10);
  const res = await fetch('/api/challenge/workouts/rollup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track, workout_num, week_num, date: STATE.date })
  });
  const data = await res.json();
  if (data.ok) {
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    if (data.rolled_up) {
      showToast(`💪 Rolled up ${data.sets} sets (${data.volume_kg.toLocaleString()} kg) → Today & Check-In Sheet!`);
    }
  }
};

// ── WEEK-OVER-WEEK PROGRESS TABLE ON CHECK-IN SHEET (TAB 3) ──────────────────
function injectWeekOverWeekOnCheckinTab() {
  const panel = document.getElementById('panel-checkin');
  if (!panel || document.getElementById('wow-progress-card')) return;
  const card = document.createElement('div');
  card.id = 'wow-progress-card';
  card.className = 'card';
  panel.insertBefore(card, panel.children[2] || null);
}

function renderWeekOverWeekTable() {
  const card = document.getElementById('wow-progress-card');
  if (!card || !window.PROGRESS_SUMMARY) return;
  const curWk = getActiveSheetWeek();
  const rowsHtml = (PROGRESS_SUMMARY.weeks || []).map(w => {
    const isCur = w.week_num === curWk;
    const wtStr = w.avg_weight_kg !== null ? `${w.avg_weight_kg.toFixed(2)} kg` : '—';
    const deltaStr = w.weight_change_vs_prev_kg !== null
      ? `<span style="color:${w.weight_change_vs_prev_kg <= 0 ? '#3DFF4F' : '#f87171'}">${w.weight_change_vs_prev_kg > 0 ? '+' : ''}${w.weight_change_vs_prev_kg.toFixed(2)} kg</span>`
      : '—';
    const stepsStr = w.avg_steps > 0 ? `${w.avg_steps.toLocaleString()} / ${(w.target_steps/1000).toFixed(0)}k` : '—';
    const calStr = w.avg_calories > 0 ? `${w.avg_calories} kcal · ${w.avg_protein_g}g P` : '—';
    const volStr = w.workout_volume_kg > 0 ? `${w.workout_volume_kg.toLocaleString()} kg (${w.workout_sets_logged}s)` : '—';
    const pBadge = w.photos_count >= 3
      ? `✅ 3/3`
      : (w.week_num === 1 && w.photos_count === 0)
      ? `<span style="color:#38bdf8;font-weight:700">🚫 No Photos (Wk 1 Fri)</span>`
      : `${w.photos_count}/3 (${w.poses_logged.join(',') || 'none'})`;
    const wkLabel = w.week_num === 0
      ? `Start (Mon Day 1)`
      : w.week_num === 1
      ? `Week 1 (Fri · No Photos)`
      : `Week ${w.week_num} (Fri)`;
    return `<tr style="${isCur ? 'background:rgba(61,255,79,0.1);font-weight:700;' : ''}cursor:pointer" onclick="document.getElementById('ci-week-select').value='${w.week_num}';loadWeekSheet('${w.week_num}')">
      <td><strong>${wkLabel}</strong></td>
      <td>${w.days_logged}/7</td>
      <td>${wtStr} <small style="color:var(--muted)">(T:${w.target_weight_kg})</small></td>
      <td>${deltaStr}</td>
      <td>${stepsStr}</td>
      <td>${calStr}</td>
      <td>${w.gym_sessions} GYM / ${w.cardio_sessions} CARDIO</td>
      <td>${volStr}</td>
      <td>${pBadge}</td>
    </tr>`;
  }).join('');

  card.innerHTML = `
    <div class="card-header">
      <div class="card-title">📈 Week-over-Week Progress Comparison (Click any week to view)</div>
      <span class="badge badge-green">Pre-Coaching + Weeks 1–8</span>
    </div>
    <div class="table-wrap">
      <table class="cs-table">
        <thead>
          <tr><th>Week</th><th>Days</th><th>Avg Wt (Target)</th><th>Δ vs Prev Wk</th><th>Avg Steps</th><th>Avg Cal & Prot</th><th>Sessions</th><th>Strength Volume</th><th>3 Photos</th></tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

// ── 3 PROGRESS PHOTOS (FRONT, SIDE, BACK) & WEEKLY SUBMISSION ────────────────
function upgradeThreePhotoWeeklyVault() {
  const listEl = document.getElementById('photos-vault-list');
  if (!listEl) return;
  const card = listEl.closest('.card');
  if (!card || card.dataset.upgraded === '1') return;
  card.dataset.upgraded = '1';
  card.innerHTML = `
    <div class="card-header" style="flex-wrap:wrap;gap:6px">
      <div class="card-title">📸 Weekly 3-Photo Check-In (<span id="photo-active-wk-label">Week 1</span>: Side · Front · Back)</div>
      <div style="display:flex;gap:6px;align-items:center;font-size:0.74rem;flex-wrap:wrap">
        <label class="btn btn-sm" style="cursor:pointer;padding:2px 8px;font-size:0.68rem" title="Auto-slice a 3-pose collage into Side, Front & Back">
          ✂️ Split 3-Pose Collage
          <input type="file" accept="image/*" style="display:none" onchange="handleThreePoseCollageUpload(event)" />
        </label>
        <span>Compare:</span>
        <select id="photo-cmp-wk-a" onchange="renderThreePhotoSlots();renderCoachWowSideBySide()" style="width:115px"><option value="0" selected>Start (Mon Day 1)</option><option value="1">Wk 1 (Fri · No Pic)</option><option value="2">Wk 2 (Fri)</option><option value="3">Wk 3 (Fri)</option><option value="4">Wk 4 (Fri)</option><option value="5">Wk 5 (Fri)</option><option value="6">Wk 6 (Fri)</option><option value="7">Wk 7 (Fri)</option><option value="8">Wk 8 (Fri)</option></select>
        <span>vs</span>
        <select id="photo-cmp-wk-b" onchange="renderThreePhotoSlots();renderCoachWowSideBySide()" style="width:115px"><option value="0">Start (Mon Day 1)</option><option value="1">Wk 1 (Fri · No Pic)</option><option value="2" selected>Wk 2 (Fri)</option><option value="3">Wk 3 (Fri)</option><option value="4">Wk 4 (Fri)</option><option value="5">Wk 5 (Fri)</option><option value="6">Wk 6 (Fri)</option><option value="7">Wk 7 (Fri)</option><option value="8">Wk 8 (Fri)</option></select>
      </div>
    </div>
    <div id="photo-schedule-rule-banner" style="margin-bottom:0.65rem;padding:0.5rem 0.7rem;border-radius:8px;font-size:0.74rem"></div>
    <div id="three-photo-slots" class="grid-3" style="margin-bottom:0.75rem"></div>
    <div id="three-photo-comparison"></div>
  `;
}

function _findPhotoForWeekAndPose(photos, wk, pose) {
  const exact = photos.find(p => Number(p.week_num) === Number(wk) && p.pose === pose);
  if (exact) return exact;
  // If viewing Start Check-In (wk=0) and baseline photos were uploaded under wk=1 on Monday start, show them:
  if (Number(wk) === 0) {
    return photos.find(p => Number(p.week_num) === 1 && p.pose === pose) || null;
  }
  return null;
}

function renderThreePhotoSlots() {
  const slotsEl = document.getElementById('three-photo-slots');
  if (!slotsEl) return;
  const wk = getActiveSheetWeek();
  const lbl = document.getElementById('photo-active-wk-label');
  if (lbl) {
    lbl.textContent = wk === 0
      ? 'Start Check-In · Day 1 Monday'
      : wk === 1
      ? 'Week 1 · Friday Check-In (No Photos Needed)'
      : `Week ${wk} · Friday Check-In`;
  }
  const ruleBanner = document.getElementById('photo-schedule-rule-banner');
  if (ruleBanner) {
    if (wk === 1) {
      ruleBanner.style.background = 'rgba(56,189,248,0.12)';
      ruleBanner.style.border = '1px solid rgba(56,189,248,0.4)';
      ruleBanner.style.color = '#e0f2fe';
      ruleBanner.innerHTML = '🚫 <strong>First Friday Check-In (Week 1): No photos required this Friday!</strong> You already submitted your starting photos on Day 1 Monday. Weekly Friday progress photos resume on <strong>Week 2 Friday</strong>.';
    } else if (wk === 0) {
      ruleBanner.style.background = 'rgba(61,255,79,0.10)';
      ruleBanner.style.border = '1px solid rgba(61,255,79,0.35)';
      ruleBanner.style.color = '#dcfce7';
      ruleBanner.innerHTML = '📸 <strong>Start Check-In (Day 1 Monday):</strong> Upload your 3 Starting Photos (Side · Front · Back) &amp; log your fasted Starting Weight.';
    } else {
      ruleBanner.style.background = 'rgba(61,255,79,0.10)';
      ruleBanner.style.border = '1px solid rgba(61,255,79,0.35)';
      ruleBanner.style.color = '#dcfce7';
      ruleBanner.innerHTML = `📸 <strong>Week ${wk} Friday Check-In:</strong> Upload your 3 Friday Progress Photos (Side · Front · Back) alongside your Friday weigh-in.`;
    }
  }
  const photos = (STATE.overview && STATE.overview.progress_photos) || (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.photos) || [];
  const poses = ['Side', 'Front', 'Back'];

  slotsEl.innerHTML = poses.map(pose => {
    const rec = _findPhotoForWeekAndPose(photos, wk, pose);
    const noPhotoNeededWk1 = wk === 1 && !rec;
    const imgHtml = rec && rec.photo_data_url
      ? `<img src="${rec.photo_data_url}" style="width:100%;height:130px;object-fit:contain;background:#070a08;border-radius:8px;margin-bottom:6px;border:1px solid var(--green)"/>`
      : `<div style="width:100%;height:130px;border-radius:8px;border:1px dashed ${noPhotoNeededWk1 ? 'rgba(56,189,248,0.45)' : 'var(--border)'};display:flex;align-items:center;justify-content:center;color:${noPhotoNeededWk1 ? '#38bdf8' : 'var(--muted)'};font-size:0.72rem;padding:0.4rem;margin-bottom:6px">${noPhotoNeededWk1 ? '🚫 No photo needed on Week 1 Friday (Sent Monday)' : rec ? '✅ Logged' : `No ${pose} photo`}</div>`;
    return `<div style="padding:0.6rem;border-radius:10px;background:var(--surface-2);border:1px solid ${rec ? 'var(--green)' : 'var(--border)'};text-align:center">
      <div style="font-weight:700;font-size:0.78rem;margin-bottom:4px">${rec ? '✅' : (noPhotoNeededWk1 ? '🚫' : '📷')} ${pose} Pose (${wk === 0 ? 'Start Mon' : 'Wk ' + wk + ' Fri'})</div>
      ${imgHtml}
      <div style="font-size:0.68rem;color:var(--muted);margin-bottom:6px">${rec ? `${rec.taken_date}${rec.weight_kg ? ' · ' + rec.weight_kg + 'kg' : ''}` : (noPhotoNeededWk1 ? 'Optional on Wk 1 Fri' : 'Fasted morning')}</div>
      <label class="btn ${noPhotoNeededWk1 ? '' : 'btn-green'} btn-sm" style="cursor:pointer;display:inline-block">
        📤 ${rec ? 'Update' : (noPhotoNeededWk1 ? 'Optional' : 'Record')} ${pose}
        <input type="file" accept="image/*" style="display:none" onchange="handlePoseFileSelect(event, ${wk}, '${pose}')"/>
      </label>
    </div>`;
  }).join('');

  const cmpEl = document.getElementById('three-photo-comparison');
  const wkA = Number(document.getElementById('photo-cmp-wk-a')?.value ?? 0);
  const wkB = Number(document.getElementById('photo-cmp-wk-b')?.value ?? wk);
  if (cmpEl) {
    cmpEl.innerHTML = `<div style="font-size:0.74rem;font-weight:700;margin-bottom:6px;color:var(--muted)">🔍 Side-by-Side Comparison: ${wkA === 0 ? 'Start (Mon)' : 'Wk ' + wkA + ' (Fri)'} vs ${wkB === 0 ? 'Start (Mon)' : 'Wk ' + wkB + ' (Fri)'} (Side · Front · Back)</div>
      <div class="grid-3">${poses.map(pose => {
        const pA = _findPhotoForWeekAndPose(photos, wkA, pose);
        const pB = _findPhotoForWeekAndPose(photos, wkB, pose);
        const box = (p, w) => p && p.photo_data_url
          ? `<img src="${p.photo_data_url}" style="width:100%;height:85px;object-fit:cover;border-radius:6px"/>`
          : `<div style="height:85px;border-radius:6px;background:var(--surface-2);display:flex;align-items:center;justify-content:center;font-size:0.68rem;color:var(--muted)">${w === 0 ? 'Start' : 'Wk ' + w}: ${w === 1 ? 'No Pic (Fri)' : (p ? 'Logged' : 'Empty')}</div>`;
        return `<div style="padding:6px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border)"><div style="font-size:0.7rem;font-weight:700;text-align:center;margin-bottom:4px">${pose}</div><div class="grid-2">${box(pA, wkA)}${box(pB, wkB)}</div></div>`;
      }).join('')}</div>`;
  }
}

window.handlePoseFileSelect = function(event, weekNum, pose) {
  const file = event.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    const img = new Image();
    img.onload = async function() {
      const canvas = document.createElement('canvas');
      const maxDim = 600;
      let w = img.width, h = img.height;
      if (w > maxDim || h > maxDim) {
        if (w > h) { h = Math.round(h * maxDim / w); w = maxDim; }
        else { w = Math.round(w * maxDim / h); h = maxDim; }
      }
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      const c = (STATE.overview && STATE.overview.checkin) || {};
      const res = await fetch('/api/challenge/photos/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_num: weekNum, pose, taken_date: STATE.date, weight_kg: c.weight_kg || null, photo_data_url: canvas.toDataURL('image/jpeg', 0.8) })
      });
      const data = await res.json();
      if (data.ok) {
        if (STATE.overview) STATE.overview.progress_photos = data.photos;
        await refreshProgressSummary();
        showToast(`📸 Recorded ${pose} photo for Week ${weekNum}!`);
      }
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
};

// ── UNIVERSAL BUTTON AFFORDANCE & LOADING FEEDBACK (DESKTOP + MOBILE) ────────
window._lastClickedActionBtn = null;

window.setButtonBusy = function(btn, busyText) {
  const el = btn || window._lastClickedActionBtn;
  if (!el) return null;
  if (!el.hasAttribute('data-orig-html')) {
    el.setAttribute('data-orig-html', el.innerHTML);
  }
  el.disabled = true;
  el.classList.remove('btn-done-flash', 'btn-pressed');
  el.classList.add('btn-loading');
  if (busyText) {
    el.textContent = busyText;
  }
  return el;
};

window.clearButtonBusy = function(btn, doneText) {
  const el = btn;
  if (!el) return;
  const origHtml = el.getAttribute('data-orig-html');
  el.disabled = false;
  el.classList.remove('btn-loading', 'btn-pressed');
  if (doneText) {
    el.classList.add('btn-done-flash');
    el.textContent = doneText;
    setTimeout(() => {
      el.classList.remove('btn-done-flash');
      if (origHtml != null) {
        el.innerHTML = origHtml;
        el.removeAttribute('data-orig-html');
      }
    }, 1500);
  } else if (origHtml != null) {
    el.innerHTML = origHtml;
    el.removeAttribute('data-orig-html');
  }
};

(function initGlobalButtonAffordance() {
  if (window._csBtnAffordanceWired) return;
  window._csBtnAffordanceWired = true;

  document.addEventListener('pointerdown', function(ev) {
    const btn = ev.target && ev.target.closest ? ev.target.closest('button, .btn, .op-train-btn') : null;
    if (!btn || btn.disabled) return;
    window._lastClickedActionBtn = btn;
    window._lastClickedActionTime = Date.now();
    btn.classList.add('btn-pressed');
    setTimeout(() => btn.classList.remove('btn-pressed'), 260);
  }, { passive: true });

  // Automatically show a tactile loading state on any button that triggers a network POST/DELETE
  if (typeof window.fetch === 'function' && !window._csFetchWrapped) {
    window._csFetchWrapped = true;
    const origFetch = window.fetch.bind(window);
    window.fetch = async function(input, init) {
      const method = ((init && init.method) || 'GET').toUpperCase();
      const recentBtn = (window._lastClickedActionBtn && (Date.now() - (window._lastClickedActionTime || 0) < 600))
        ? window._lastClickedActionBtn
        : null;
      const autoManaged = recentBtn && method !== 'GET' && !recentBtn.classList.contains('btn-loading');
      if (autoManaged) {
        recentBtn.classList.add('btn-loading');
      }
      try {
        const res = await origFetch(input, init);
        return res;
      } finally {
        if (autoManaged && recentBtn) {
          recentBtn.classList.remove('btn-loading');
          recentBtn.classList.add('btn-done-flash');
          setTimeout(() => recentBtn.classList.remove('btn-done-flash'), 900);
        }
      }
    };
  }
})();

// ── REAL GARMIN & MYFITNESSPAL SAVE + CONNECT + CSV IMPORT (TAB 4) ───────────
function upgradeIntegrationsSaveAndImport() {
  const saveBtn = document.getElementById('btn-cfg-save-main') || document.querySelector('button[onclick*="saveIntegrationsConfig"]');
  if (saveBtn && !document.getElementById('sync-connection-report')) {
    const statusBox = document.createElement('div');
    statusBox.id = 'sync-connection-report';
    statusBox.style.cssText = 'margin-top:10px;padding:10px;border-radius:10px;background:var(--surface-2);border:1px solid var(--border);font-size:0.74rem;';
    saveBtn.parentNode.insertBefore(statusBox, saveBtn.nextSibling);
  }
  const existingBox = document.getElementById('sync-connection-report');
  if (existingBox && !document.getElementById('sync-direct-import-box')) {
    const importBox = document.createElement('div');
    importBox.id = 'sync-direct-import-box';
    importBox.style.cssText = 'margin-top:10px;padding:10px;border-radius:10px;background:var(--surface-2);border:1px dashed var(--border);font-size:0.74rem;';
    importBox.innerHTML = `
      <strong>📂 Direct File Import (Garmin Connect or MyFitnessPal .csv / .json)</strong>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">
        <label class="btn btn-sm" style="cursor:pointer">⌚ Import Garmin CSV/JSON<input type="file" accept=".csv,.json" style="display:none" onchange="importSyncFile(event, 'garmin')"/></label>
        <label class="btn btn-sm" style="cursor:pointer">🥗 Import MyFitnessPal CSV/JSON<input type="file" accept=".csv,.json" style="display:none" onchange="importSyncFile(event, 'mfp')"/></label>
      </div>
    `;
    existingBox.parentNode.insertBefore(importBox, existingBox.nextSibling);
  }
  renderSavedIntegrationStatus();
}

function renderSavedIntegrationStatus() {
  const box = document.getElementById('sync-connection-report');
  if (!box) return;
  const intg = (STATE.overview && STATE.overview.integrations) || {};
  box.style.display = 'block';
  box.innerHTML = `
    <div><strong>🔐 Saved Account Status in Database:</strong></div>
    <div style="margin-top:4px">• <strong>Garmin Email:</strong> ${intg.garmin_email || '<em>Not saved yet</em>'} ${intg.garmin_password_set ? '(Password/Token set)' : ''} · Last Sync: ${intg.garmin_last_sync || 'Never'}</div>
    <div>• <strong>Nutrition (Calories, Protein &amp; Water):</strong> Add manually or via MyFitnessPal / Apple Health</div>
  `;
}

window.saveIntegrationsConfig = async function(isMfaVerify, triggerBtn) {
  const box = document.getElementById('sync-connection-report');
  const mfaInput = document.getElementById('cfg-garmin-mfa-code');
  const mfaBox = document.getElementById('cfg-garmin-mfa-box');
  const mfaPrompt = document.getElementById('cfg-garmin-mfa-prompt');
  const mfaBadge = document.getElementById('cfg-garmin-mfa-badge');
  const mfaCode = (mfaInput?.value || '').trim();
  const activeBtn = window.setButtonBusy(
    triggerBtn || document.getElementById(isMfaVerify ? 'btn-cfg-verify-mfa' : 'btn-cfg-save-main'),
    isMfaVerify ? '⏳ Verifying 2FA Code...' : '⏳ Connecting to Garmin...'
  );

  if (box) {
    box.style.display = 'block';
    box.style.borderColor = 'rgba(56,189,248,0.6)';
    box.innerHTML = isMfaVerify
      ? `<div style="color:#38bdf8;font-weight:800">⏳ Verifying Garmin 2FA code &amp; completing connection...</div>`
      : `<div style="color:#38bdf8;font-weight:800">⏳ Saving account details &amp; connecting to Garmin Connect for ${STATE.date}...</div>`;
  }
  const garminVault = typeof window.getBrowserGarminVault === 'function' ? window.getBrowserGarminVault() : {};
  const rawEmail = (document.getElementById('cfg-garmin-email')?.value || garminVault.garmin_email || '').trim();
  const rawPass = document.getElementById('cfg-garmin-pass')?.value || '';
  if (rawEmail || rawPass) {
    if (typeof window.saveBrowserGarminVault === 'function') {
      window.saveBrowserGarminVault({
        garmin_email: rawEmail,
        garmin_password_b64: rawPass ? btoa(unescape(encodeURIComponent(rawPass))) : (garminVault.garmin_password_b64 || ''),
      });
    }
  }
  const payload = {
    date: STATE.date,
    garmin_email: rawEmail,
    garmin_password: rawPass,
    garmin_password_b64: rawPass ? btoa(unescape(encodeURIComponent(rawPass))) : (garminVault.garmin_password_b64 || ''),
    garmin_token_dump: garminVault.garmin_token_dump || '',
    mfa_code: mfaCode,
    nutrition_provider: document.getElementById('cfg-nutri-provider')?.value || 'myfitnesspal',
    mfp_username: document.getElementById('cfg-mfp-user')?.value || '',
    telegram_bot_token: document.getElementById('cfg-tg-token')?.value || '',
    telegram_chat_id: document.getElementById('cfg-tg-chat')?.value || '',
  };
  try {
    const res = await fetch('/api/challenge/sync/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.integrations && typeof window.saveBrowserGarminVault === 'function') {
      window.saveBrowserGarminVault(data.integrations);
    }
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    if (typeof window.pullServerBackupIntoBrowserVault === 'function') {
      window.pullServerBackupIntoBrowserVault();
    }

    if (data.needs_mfa) {
      window.clearButtonBusy(activeBtn, '🔐 Enter 2FA Code');
      if (mfaBox) {
        mfaBox.style.borderColor = '#fbbf24';
        mfaBox.style.background = 'rgba(251,191,36,0.14)';
      }
      if (mfaBadge) {
        mfaBadge.textContent = '🔐 Enter 6-Digit Code';
        mfaBadge.className = 'badge badge-amber';
      }
      if (mfaPrompt) {
        mfaPrompt.innerHTML = `<strong style="color:#fbbf24">${data.garmin_status || '🔐 Garmin sent a 6-digit verification code to your email or phone. Enter it below and click Verify 2FA Code & Connect.'}</strong>`;
      }
      if (mfaInput) mfaInput.focus();
      if (box) {
        box.style.display = 'block';
        box.style.borderColor = '#fbbf24';
        box.innerHTML = `<div style="color:#fbbf24;font-weight:800">🔐 Garmin 2-Factor Auth Required — enter the 6-digit code above and click "Verify 2FA Code &amp; Connect".</div>`;
      }
      showToast('🔐 Enter the 6-digit Garmin 2FA code sent to your email/phone!');
      return;
    }

    if (mfaInput) mfaInput.value = '';
    const isConnected = Boolean(
      (data.integrations && data.integrations.garmin_connected) ||
      (data.garmin_status && data.garmin_status.includes('✅'))
    );
    if (isConnected) {
      if (mfaBox) {
        mfaBox.style.borderColor = 'rgba(61,255,79,0.45)';
        mfaBox.style.background = 'rgba(61,255,79,0.08)';
      }
      if (mfaBadge) {
        mfaBadge.textContent = '✅ Connected (Mobile Sync Ready)';
        mfaBadge.className = 'badge badge-green';
      }
    }
    if (box) {
      box.style.display = 'block';
      box.style.borderColor = isConnected ? 'rgba(61,255,79,0.55)' : 'rgba(251,191,36,0.55)';
      box.innerHTML = `
        <div style="color:${isConnected ? 'var(--green)' : '#fbbf24'};font-weight:800;margin-bottom:4px">
          ${isConnected ? '✅ Garmin Connected &amp; Saved!' : 'ℹ️ Account Saved — Check Garmin Status Below:'}
        </div>
        <div>• <strong>Garmin:</strong> ${data.garmin_status || 'Saved'}</div>
        <div>• <strong>Nutrition:</strong> ${data.mfp_status || 'Manual / Apple Health ready'}</div>
      `;
    }
    window.clearButtonBusy(activeBtn, isConnected ? '✅ Connected!' : '✅ Saved');
    showToast(isConnected ? '✅ Garmin connected & synced!' : `ℹ️ ${data.garmin_status || 'Saved settings'}`);
  } catch (err) {
    window.clearButtonBusy(activeBtn);
    if (box) {
      box.style.display = 'block';
      box.style.borderColor = '#f87171';
      box.innerHTML = `<div style="color:#f87171;font-weight:800">⚠️ Connection request failed — please check your internet connection and try again.</div>`;
    }
    showToast('⚠️ Could not reach server to save Garmin settings.');
  }
};

window.importSyncFile = function(event, source) {
  const file = event.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async function(ev) {
    const res = await fetch('/api/challenge/sync/import-data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, content: ev.target.result, date: STATE.date })
    });
    const data = await res.json();
    if (data.ok) {
      await loadOverview(STATE.date);
      await refreshProgressSummary();
      showToast(`✅ Imported ${data.imported_count} real ${source.toUpperCase()} record(s)!`);
    }
  };
  reader.readAsText(file);
};

window.triggerLiveSync = async function(triggerBtn) {
  const emailEl = document.getElementById('cfg-garmin-email');
  const passEl = document.getElementById('cfg-garmin-pass');
  const mfpEl = document.getElementById('cfg-mfp-user');
  const box = document.getElementById('sync-connection-report');
  const activeBtn = window.setButtonBusy(
    triggerBtn || document.getElementById('btn-cfg-sync-live') || document.getElementById('btn-sync-now'),
    '⏳ Syncing Garmin...'
  );
  if (box) {
    box.style.display = 'block';
    box.style.borderColor = 'rgba(56,189,248,0.6)';
    box.innerHTML = `<div style="color:#38bdf8;font-weight:800">⏳ Pulling live Steps, Sleep, Scale Weight &amp; Workouts from Garmin Connect for ${STATE.date}...</div>`;
  }
  try {
    const garminVault = typeof window.getBrowserGarminVault === 'function' ? window.getBrowserGarminVault() : {};
    const rawEmail = (emailEl && emailEl.value ? emailEl.value : (garminVault.garmin_email || '')).trim();
    const rawPass = passEl && passEl.value ? passEl.value : '';
    const res = await fetch('/api/challenge/sync/live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: STATE.date,
        garmin_email: rawEmail,
        garmin_password: rawPass,
        garmin_password_b64: rawPass ? btoa(unescape(encodeURIComponent(rawPass))) : (garminVault.garmin_password_b64 || ''),
        garmin_token_dump: garminVault.garmin_token_dump || '',
        mfp_username: mfpEl ? mfpEl.value : '',
      }),
    });
    const data = await res.json();
    if (data.integrations && typeof window.saveBrowserGarminVault === 'function') {
      window.saveBrowserGarminVault(data.integrations);
    }
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    if (typeof window.pullServerBackupIntoBrowserVault === 'function') {
      window.pullServerBackupIntoBrowserVault();
    }
    const msg = (data.messages && data.messages.join(' · ')) || 'Sync completed';
    if (box) {
      box.style.display = 'block';
      box.style.borderColor = data.ok ? 'rgba(61,255,79,0.55)' : 'rgba(251,191,36,0.55)';
      box.innerHTML = `<div style="color:${data.ok ? 'var(--green)' : '#fbbf24'};font-weight:800">${data.ok ? '✅' : 'ℹ️'} ${msg}</div>`;
    }
    if (!data.ok && msg.toLowerCase().includes('tab 4')) {
      if (typeof switchTab === 'function') switchTab('integrations');
      if (passEl) passEl.focus();
    }
    window.clearButtonBusy(activeBtn, data.ok ? '✅ Synced!' : 'ℹ️ Check Status');
    showToast(data.ok ? `🔄 ${msg}` : `ℹ️ ${msg}`);
  } catch (err) {
    window.clearButtonBusy(activeBtn);
    if (box) {
      box.style.display = 'block';
      box.style.borderColor = '#f87171';
      box.innerHTML = `<div style="color:#f87171;font-weight:800">⚠️ Could not reach Garmin sync endpoint.</div>`;
    }
    showToast('⚠️ Could not reach Garmin sync service.');
  }
};

// ── CLEAN 9:16 INSTAGRAM SCOREBOARD PNG (STATS-ONLY, WEIGHT HIDDEN) ──────────
window.downloadInstagramScoreboardPng = async function() {
  const c = (STATE.overview && STATE.overview.checkin) || {};
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1920;
  const ctx = canvas.getContext('2d');

  const grad = ctx.createLinearGradient(0, 0, 1080, 1920);
  grad.addColorStop(0, '#050806');
  grad.addColorStop(0.5, '#0b140d');
  grad.addColorStop(1, '#050806');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 1080, 1920);

  ctx.strokeStyle = 'rgba(61,255,79,0.45)';
  ctx.lineWidth = 4;
  ctx.strokeRect(48, 80, 984, 1760);

  ctx.fillStyle = '#3DFF4F';
  ctx.font = 'italic 900 62px sans-serif';
  ctx.fillText('CS FITNESS · 8-WEEK CHALLENGE', 96, 195);

  ctx.fillStyle = '#ffffff';
  ctx.font = '700 40px sans-serif';
  ctx.fillText(`DAILY SCOREBOARD · ${STATE.date}`, 96, 265);

  const sleepStr = c.sleep_str || (c.sleep_mins > 0 ? `${Math.floor(c.sleep_mins / 60)}h ${c.sleep_mins % 60}m` : '—');
  const tiles = [
    { label: '1. STEPS (GARMIN / APPLE)', val: Number(c.steps || 0).toLocaleString(), sub: `Target: ${(c.step_target || 10000).toLocaleString()}`, col: '#3DFF4F' },
    { label: '2. CALORIES (MFP / MANUAL)', val: `${c.calories || 0} kcal`, sub: 'Daily Nutrition Target', col: '#ffffff' },
    { label: '3. PROTEIN', val: `${c.protein_g || 0}g`, sub: 'Target: 150g+', col: '#3DFF4F' },
    { label: '4. WATER INTAKE', val: `${Number(c.water_l || 0).toFixed(2)}L`, sub: 'Target: 3.66L', col: '#38bdf8' },
    { label: '5. SLEEP (GARMIN / APPLE)', val: sleepStr, sub: 'Target: 8h 00m', col: '#ffffff' },
    { label: '6. TRAINING', val: c.training_type || 'REST', sub: c.class_attended || 'Daily Session', col: '#3DFF4F' },
  ];

  tiles.forEach((t, i) => {
    const colIdx = i % 2;
    const rowIdx = Math.floor(i / 2);
    const x = 96 + colIdx * 456;
    const y = 320 + rowIdx * 320;
    ctx.fillStyle = 'rgba(255,255,255,0.04)';
    ctx.fillRect(x, y, 432, 290);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, 432, 290);

    ctx.fillStyle = '#9ca3af';
    ctx.font = '700 24px sans-serif';
    ctx.fillText(t.label, x + 28, y + 58);

    ctx.fillStyle = t.col;
    ctx.font = '900 58px sans-serif';
    ctx.fillText(String(t.val), x + 28, y + 165);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '600 24px sans-serif';
    ctx.fillText(String(t.sub).slice(0, 26), x + 28, y + 240);
  });

  const moments = ((window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || []).filter(m => m.date === STATE.date && m.photo_data_url).slice(0, 4);
  for (let i = 0; i < moments.length; i++) {
    const m = moments[i];
    const img = await new Promise(r => { const im = new Image(); im.onload = () => r(im); im.onerror = () => r(null); im.src = m.photo_data_url; });
    if (img) {
      const mx = 96 + i * 226;
      ctx.drawImage(img, mx, 1310, 210, 210);
      ctx.strokeStyle = '#3DFF4F'; ctx.lineWidth = 2; ctx.strokeRect(mx, 1310, 210, 210);
      ctx.fillStyle = '#3DFF4F'; ctx.font = '700 20px sans-serif'; ctx.fillText(m.slot, mx + 8, 1550);
    }
  }

  ctx.fillStyle = '#3DFF4F';
  ctx.font = '700 34px sans-serif';
  ctx.fillText('#CSFitness  #8WeekChallenge  #WinTheDay', 96, 1690);
  ctx.fillStyle = '#64748b';
  ctx.font = '600 26px sans-serif';
  ctx.fillText('Garmin / Apple Health + MFP / Manual Nutrition · Scale weight kept private', 96, 1750);

  const a = document.createElement('a');
  a.download = `cs-fitness-daily-snapshot-${STATE.date}.png`;
  a.href = canvas.toDataURL('image/png');
  a.click();
  showToast('📸 Downloaded End-of-Day Daily Snapshot PNG!');
};

// ── IN-APP WEEKLY CHECK-IN SUBMISSION & COACH CHRIS REVIEW INBOX ─────────────
function renderWeeklySubmissionState() {
  if (!window.PROGRESS_SUMMARY) return;
  const wk = getActiveSheetWeek();
  const wkObj = (PROGRESS_SUMMARY.weeks || []).find(w => Number(w.week_num) === wk) || {};
  const badge = document.getElementById('wk-submission-status-badge');
  const commentsEl = document.getElementById('wk-challenger-comments');
  const feedbackEl = document.getElementById('wk-coach-feedback-text');
  if (badge) {
    const st = wkObj.submission_status || 'Not Submitted';
    badge.textContent = st === 'Reviewed' ? '✅ Reviewed by Coach Chris' : (st === 'Submitted' ? '📤 Submitted to Coach' : 'Not Submitted');
    badge.className = 'badge ' + (st === 'Not Submitted' ? '' : 'badge-green');
  }
  if (commentsEl && document.activeElement !== commentsEl) {
    commentsEl.value = wkObj.challenger_comments || '';
  }
  if (feedbackEl) {
    feedbackEl.textContent = wkObj.coach_feedback
      ? wkObj.coach_feedback
      : 'No coach feedback yet for this week. Submit your check-in below so Chris can review it in the Coach Portal.';
    feedbackEl.style.color = wkObj.coach_feedback ? '#fff' : 'var(--muted)';
  }
}

window.submitWeeklyCheckinInApp = async function() {
  const wk = getActiveSheetWeek();
  const comments = document.getElementById('wk-challenger-comments')?.value || '';
  if (window.renderWeeklyCheckinCardCanvas) await window.renderWeeklyCheckinCardCanvas();
  const canvas = document.getElementById('weekly-checkin-card-canvas');
  const card_data_url = canvas ? canvas.toDataURL('image/jpeg', 0.85) : '';
  const res = await fetch('/api/challenge/weekly-checkin/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ week_num: wk, challenger_comments: comments, card_data_url }),
  });
  const data = await res.json();
  if (data.ok) {
    await refreshProgressSummary();
    showToast(`✅ Week ${wk} Stylised Card & Write-Up saved for Coach Chris!`);
  }
};

function renderCoachCheckinInbox() {
  const box = document.getElementById('coach-checkin-inbox-list');
  if (!box || !window.PROGRESS_SUMMARY) return;
  const subs = PROGRESS_SUMMARY.weekly_submissions || [];
  const badge = document.getElementById('coach-inbox-badge');
  if (badge) badge.textContent = `${subs.length} Check-In(s) in Inbox`;
  if (!subs.length) {
    box.innerHTML = `<div style="padding:0.75rem;color:var(--muted);font-size:0.76rem">No weekly check-ins submitted yet. On Tab 3 (Weekly Check-In), click <strong>✅ Submit Weekly Check-In (In-App)</strong> to send a week here for Coach Chris to review.</div>`;
    return;
  }
  box.innerHTML = subs.map(s => `
    <div style="padding:0.75rem;border-radius:10px;background:var(--surface-2);border:1px solid ${s.status === 'Reviewed' ? 'var(--green)' : 'var(--border)'};margin-bottom:0.65rem">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.45rem">
        <div>
          <strong style="color:#fff;font-size:0.86rem">👤 ${s.client_name} — Week ${s.week_num} Check-In</strong>
          <span class="badge ${s.status === 'Reviewed' ? 'badge-green' : 'badge-blue'}" style="margin-left:0.4rem">${s.status}</span>
        </div>
        <div style="font-size:0.72rem;color:var(--muted)">
          Avg Weight: <strong style="color:#fff">${s.avg_weight_kg ?? '—'} kg</strong> ·
          Avg Steps: <strong style="color:var(--green)">${(s.avg_steps || 0).toLocaleString()}</strong> ·
          Avg Cal/Prot: <strong style="color:#fff">${s.avg_calories || 0} kcal / ${s.avg_protein_g || 0}g P</strong> ·
          Photos: <strong>${s.photos_count || 0}/3</strong>
        </div>
      </div>
      <div style="font-size:0.75rem;color:#cbd5e1;margin-bottom:0.5rem;padding:0.45rem 0.6rem;background:#080b09;border-radius:6px">
        <strong>Challenger Write-Up:</strong> ${s.challenger_comments || '<em>No comments added</em>'}
      </div>
      ${s.card_data_url ? `<div style="margin-bottom:0.55rem"><img src="${s.card_data_url}" alt="Week ${s.week_num} Card" style="max-height:220px;border-radius:8px;border:1px solid var(--green);cursor:pointer" onclick="window.open(this.src,'_blank')" title="Click to view full Stylised Weekly PNG Card"/></div>` : ''}
      <div style="display:grid;grid-template-columns:1fr 130px 120px auto;gap:0.45rem;align-items:center">
        <input type="text" id="coach-fb-${s.profile_id}-${s.week_num}" value="${(s.coach_feedback || '').replace(/"/g, '&quot;')}" placeholder="Coach Chris feedback & next week focus..." style="font-size:0.75rem" />
        <input type="number" id="coach-cal-${s.profile_id}-${s.week_num}" value="${s.target_calories || 2173}" title="Adjust Daily Calorie Target" style="font-size:0.75rem" />
        <input type="number" id="coach-prot-${s.profile_id}-${s.week_num}" value="${s.target_protein_g || 150}" title="Adjust Protein Target (g)" style="font-size:0.75rem" />
        <button class="btn btn-green btn-sm" onclick="saveCoachWeeklyReview(${s.profile_id}, ${s.week_num})">💬 Save Coach Review</button>
      </div>
    </div>
  `).join('');
}

window.saveCoachWeeklyReview = async function(profileId, weekNum) {
  const fb = document.getElementById(`coach-fb-${profileId}-${weekNum}`)?.value || '';
  const cal = document.getElementById(`coach-cal-${profileId}-${weekNum}`)?.value;
  const prot = document.getElementById(`coach-prot-${profileId}-${weekNum}`)?.value;
  const res = await fetch('/api/challenge/weekly-checkin/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      profile_id: profileId,
      week_num: weekNum,
      coach_feedback: fb,
      new_target_calories: cal ? Number(cal) : null,
      new_target_protein_g: prot ? Number(prot) : null,
    }),
  });
  const data = await res.json();
  if (data.ok) {
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    showToast(`✅ Coach Chris review saved for Week ${weekNum}!`);
  }
};

function loadImageAsync(src) {
  return new Promise((resolve) => {
    if (!src) return resolve(null);
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = () => resolve(im);
    im.onerror = () => resolve(null);
    im.src = src;
  });
}

function knockOutWhiteBgToCanvas(img, removeWhite) {
  const off = document.createElement('canvas');
  off.width = img.width || 400;
  off.height = img.height || 600;
  const octx = off.getContext('2d');
  octx.drawImage(img, 0, 0);
  if (!removeWhite) return off;
  try {
    const idata = octx.getImageData(0, 0, off.width, off.height);
    const d = idata.data;
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      const maxC = Math.max(r, g, b), minC = Math.min(r, g, b);
      if (minC > 236 && (maxC - minC) < 16) {
        d[i + 3] = 0;
      } else if (minC > 220 && (maxC - minC) < 18) {
        d[i + 3] = Math.round(((236 - minC) / 16) * 255);
      }
    }
    octx.putImageData(idata, 0, 0);
  } catch (e) {}
  return off;
}

window.renderWeeklyCheckinCardCanvas = async function() {
  const canvas = document.getElementById('weekly-checkin-card-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const wk = getActiveSheetWeek();
  const prof = (STATE.overview && STATE.overview.profile) || (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.profile) || { client_name: 'Challenger', start_weight_kg: 80.0, target_weight_kg: 74.5, target_calories: 2173, target_protein_g: 150 };
  const wkObj = ((window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.weeks) || []).find(w => Number(w.week_num) === wk) || {};
  const photos = (STATE.overview && STATE.overview.progress_photos) || (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.photos) || [];
  const removeWhite = Boolean(document.getElementById('wk-card-cutout-toggle')?.checked);

  ctx.fillStyle = '#070A08';
  ctx.fillRect(0, 0, 1200, 1350);
  ctx.fillStyle = '#3DFF4F';
  ctx.fillRect(0, 0, 1200, 10);

  // Header
  ctx.fillStyle = '#3DFF4F';
  ctx.font = '800 22px Inter, -apple-system, sans-serif';
  ctx.fillText('CS FITNESS · 8-WEEK CHALLENGE CHECK-IN', 48, 58);
  ctx.fillStyle = '#FFFFFF';
  ctx.font = '900 44px Inter, -apple-system, sans-serif';
  const wkTitle = wk === 0 ? 'PRE-COACHING PHOTOS & CHECK-IN' : (wk === 1 ? 'WEEK 1 (DAY 1) PHOTOS & CHECK-IN' : `WEEK ${wk} PROGRESS & CHECK-IN`);
  ctx.fillText(wkTitle, 48, 110);
  ctx.fillStyle = '#94A3B8';
  ctx.font = '600 22px Inter, -apple-system, sans-serif';
  ctx.fillText(`Challenger: ${prof.client_name || 'Challenger'}   ·   Start: ${prof.start_weight_kg || 80.0} kg → Goal: ${prof.target_weight_kg || 74.5} kg`, 48, 146);

  // 5-Stat Strip
  const stats = [
    ['AVG WEIGHT', wkObj.avg_weight_kg ? `${wkObj.avg_weight_kg} kg` : `${prof.start_weight_kg || 84.0} kg`, `Target ${wkObj.target_weight_kg || prof.target_weight_kg || 84.0} kg`],
    ['AVG STEPS', wkObj.avg_steps ? wkObj.avg_steps.toLocaleString() : '—', `Min ${(wkObj.target_steps || 10000).toLocaleString()}`],
    ['AVG CALORIES', wkObj.avg_calories ? `${wkObj.avg_calories} kcal` : '—', `Target ${prof.target_calories || 2173}`],
    ['AVG PROTEIN', wkObj.avg_protein_g ? `${wkObj.avg_protein_g} g` : '—', `Target ${prof.target_protein_g || 150}g`],
    ['SESSIONS', `${wkObj.gym_sessions || 0} GYM / ${wkObj.cardio_sessions || 0} CARDIO`, `${wkObj.days_logged || 0}/7 days logged`],
  ];
  stats.forEach((st, idx) => {
    const sx = 48 + idx * 224;
    ctx.fillStyle = '#0F1712';
    ctx.strokeStyle = '#1E2E23';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.roundRect(sx, 168, 210, 88, 12); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#94A3B8'; ctx.font = '700 14px Inter, sans-serif'; ctx.fillText(st[0], sx + 16, 194);
    ctx.fillStyle = '#3DFF4F'; ctx.font = '800 24px Inter, sans-serif'; ctx.fillText(st[1], sx + 16, 224);
    ctx.fillStyle = '#64748B'; ctx.font = '600 13px Inter, sans-serif'; ctx.fillText(st[2], sx + 16, 244);
  });
  await _drawThreePosesAndWriteupOnCard(ctx, wk, photos, removeWhite, wkObj);
};

async function _drawThreePosesAndWriteupOnCard(ctx, wk, photos, removeWhite, wkObj) {
  const poses = ['Side', 'Front', 'Back'];
  for (let i = 0; i < poses.length; i++) {
    const pose = poses[i];
    const px = 48 + i * 376, py = 278, pw = 352, ph = 640;
    const grad = ctx.createRadialGradient(px + pw / 2, py + ph * 0.55, 20, px + pw / 2, py + ph * 0.55, 260);
    grad.addColorStop(0, 'rgba(61, 255, 79, 0.16)');
    grad.addColorStop(1, 'rgba(12, 18, 14, 0.95)');
    ctx.fillStyle = grad;
    ctx.strokeStyle = 'rgba(61, 255, 79, 0.45)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.roundRect(px, py, pw, ph, 18); ctx.fill(); ctx.stroke();

    const rec = photos.find(p => Number(p.week_num) === wk && p.pose === pose);
    const img = rec && rec.photo_data_url ? await loadImageAsync(rec.photo_data_url) : null;
    if (img) {
      const processed = knockOutWhiteBgToCanvas(img, removeWhite);
      const scale = Math.min((pw - 24) / processed.width, (ph - 76) / processed.height);
      const dw = processed.width * scale, dh = processed.height * scale;
      ctx.drawImage(processed, px + (pw - dw) / 2, py + 54 + (ph - 66 - dh) / 2, dw, dh);
    } else {
      ctx.fillStyle = '#475569';
      ctx.font = '700 20px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`Upload ${pose} Pose`, px + pw / 2, py + ph / 2 - 10);
      ctx.font = '500 15px Inter, sans-serif';
      ctx.fillText('or use Auto-Split 3-Pose Collage', px + pw / 2, py + ph / 2 + 20);
      ctx.textAlign = 'left';
    }
    ctx.fillStyle = 'rgba(7, 10, 8, 0.85)';
    ctx.beginPath(); ctx.roundRect(px + 14, py + 12, 140, 34, 8); ctx.fill();
    ctx.fillStyle = '#3DFF4F';
    ctx.font = '800 16px Inter, sans-serif';
    ctx.fillText(`${pose.toUpperCase()} POSE`, px + 26, py + 35);
  }
  _drawWriteupBoxOnCard(ctx, wk, wkObj);
}

function _drawWriteupBoxOnCard(ctx, wk, wkObj) {
  const bx = 48, by = 942, bw = 1104, bh = 368;
  ctx.fillStyle = '#0D1410';
  ctx.strokeStyle = '#3DFF4F';
  ctx.lineWidth = 2;
  ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, 18); ctx.fill(); ctx.stroke();

  ctx.fillStyle = '#3DFF4F';
  ctx.font = '800 20px Inter, sans-serif';
  ctx.fillText(`📝 WEEKLY CHECK-IN WRITE-UP & NOTES (WEEK ${wk})`, bx + 28, by + 42);

  const rawText = (document.getElementById('wk-challenger-comments')?.value || wkObj.challenger_comments || 'Add your weekly write-up above — it renders live onto this Weekly Check-In PNG card!').trim();
  ctx.fillStyle = '#F8FAFC';
  ctx.font = '500 25px Inter, -apple-system, sans-serif';
  const words = rawText.split(/\s+/);
  let line = '', y = by + 90;
  for (let i = 0; i < words.length; i++) {
    const test = line + words[i] + ' ';
    if (ctx.measureText(test).width > bw - 56 && i > 0) {
      ctx.fillText(line.trim(), bx + 28, y);
      line = words[i] + ' ';
      y += 38;
      if (y > by + bh - 75) break;
    } else {
      line = test;
    }
  }
  if (line.trim() && y <= by + bh - 65) ctx.fillText(line.trim(), bx + 28, y);

  ctx.fillStyle = '#94A3B8';
  ctx.font = '700 17px Inter, sans-serif';
  const fb = wkObj.coach_feedback ? `💬 Coach Chris: ${wkObj.coach_feedback}` : '📲 Shared via CS Fitness 8-Week Challenge App · #CSFitness #WinTheDay';
  ctx.fillText(fb.slice(0, 105), bx + 28, by + bh - 24);
}

window.downloadWeeklyCheckinPng = async function() {
  await window.renderWeeklyCheckinCardCanvas();
  const canvas = document.getElementById('weekly-checkin-card-canvas');
  if (!canvas) return;
  const wk = getActiveSheetWeek();
  const a = document.createElement('a');
  a.download = `cs-fitness-week-${wk}-checkin.png`;
  a.href = canvas.toDataURL('image/png');
  a.click();
  showToast(`🖼️ Downloaded Stylised Week ${wk} Check-In PNG!`);
};

window.handleThreePoseCollageUpload = function(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const wk = getActiveSheetWeek();
  const reader = new FileReader();
  reader.onload = function(ev) {
    const img = new Image();
    img.onload = async function() {
      const poses = ['Side', 'Front', 'Back'];
      const hasBottomCaption = img.height > img.width * 0.72;
      const topSkip = hasBottomCaption ? Math.round(img.height * 0.08) : 0;
      const cropH = hasBottomCaption ? Math.round(img.height * 0.56) : img.height;
      const sliceW = Math.floor(img.width / 3);
      const c = (STATE.overview && STATE.overview.checkin) || {};
      for (let i = 0; i < 3; i++) {
        const sc = document.createElement('canvas');
        sc.width = 420;
        sc.height = Math.round(420 * (cropH / sliceW));
        sc.getContext('2d').drawImage(img, i * sliceW, topSkip, sliceW, cropH, 0, 0, sc.width, sc.height);
        const res = await fetch('/api/challenge/photos/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ week_num: wk, pose: poses[i], taken_date: STATE.date, weight_kg: c.weight_kg || null, photo_data_url: sc.toDataURL('image/png') })
        });
        const data = await res.json();
        if (data.ok && STATE.overview) STATE.overview.progress_photos = data.photos;
      }
      await refreshProgressSummary();
      showToast(`✂️ Auto-split 3-pose collage into Side, Front & Back for Week ${wk}!`);
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
};

window.promptQuickCoachNote = async function() {
  const wk = getActiveSheetWeek();
  const wkObj = ((window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.weeks) || []).find(w => Number(w.week_num) === wk) || {};
  const fb = window.prompt(`Paste or log Coach Chris's feedback (from Telegram / voice note) for Week ${wk}:`, wkObj.coach_feedback || '');
  if (fb === null) return;
  await fetch('/api/challenge/weekly-checkin/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ week_num: wk, coach_feedback: fb })
  });
  await refreshProgressSummary();
  showToast(`💬 Saved Coach Chris's feedback for Week ${wk}!`);
};

window.sendWeeklyTelegram = async function() {
  const week_num = getActiveSheetWeek();
  await window.renderWeeklyCheckinCardCanvas();
  const canvas = document.getElementById('weekly-checkin-card-canvas');
  const photo_data_url = canvas ? canvas.toDataURL('image/png') : '';
  const writeup = document.getElementById('wk-challenger-comments')?.value || '';
  const baseSummary = document.getElementById('tg-summary-box')?.value || '';
  const custom_message = writeup ? `${baseSummary}\n\n📝 Weekly Write-Up:\n${writeup}` : baseSummary;

  await window.submitWeeklyCheckinInApp();
  const res = await fetch('/api/challenge/telegram/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ week_num, custom_message, photo_data_url }),
  });
  const data = await res.json();
  if (data.sent_via_api) {
    showToast(`✈️ Sent Week ${week_num} PNG Card & Summary directly to Telegram!`);
  } else {
    await window.downloadWeeklyCheckinPng();
    try { await navigator.clipboard.writeText(custom_message); } catch (e) {}
    if (data.deep_link_url) {
      const linkBtn = document.getElementById('tg-direct-link');
      if (linkBtn) { linkBtn.href = data.deep_link_url; linkBtn.style.display = 'inline-flex'; }
    }
    showToast(`🖼️ Downloaded Week ${week_num} PNG & copied Telegram summary — ready to drop into Telegram!`);
  }
};

function renderCoachWowSideBySide() {
  const panel = document.getElementById('coach-wow-side-by-side-panel');
  if (!panel || !window.PROGRESS_SUMMARY) return;
  const weeks = window.PROGRESS_SUMMARY.weeks || [];
  const photos = (STATE.overview && STATE.overview.progress_photos) || window.PROGRESS_SUMMARY.photos || [];
  const wkA = Number(document.getElementById('photo-cmp-wk-a')?.value ?? 1);
  const wkB = Number(document.getElementById('photo-cmp-wk-b')?.value ?? Math.max(2, getActiveSheetWeek()));
  const wA = weeks.find(w => Number(w.week_num) === wkA) || { week_num: wkA };
  const wB = weeks.find(w => Number(w.week_num) === wkB) || { week_num: wkB };
  const poses = ['Side', 'Front', 'Back'];

  const poseRows = poses.map(pose => {
    const pA = _findPhotoForWeekAndPose(photos, wkA, pose);
    const pB = _findPhotoForWeekAndPose(photos, wkB, pose);
    const cell = (p, w) => p && p.photo_data_url
      ? `<img src="${p.photo_data_url}" style="width:100%;height:110px;object-fit:contain;background:#070a08;border-radius:6px;border:1px solid rgba(61,255,79,0.4)"/>`
      : `<div style="height:110px;border-radius:6px;background:#070a08;border:1px dashed var(--border);display:flex;align-items:center;justify-content:center;font-size:0.68rem;color:var(--muted)">${w === 0 ? 'Start Mon' : 'Wk ' + w + ' Fri'}: ${w === 1 ? 'No Pic Needed' : 'No ' + pose}</div>`;
    return `<div style="padding:6px;border-radius:8px;background:#0b110d;border:1px solid var(--border)">
      <div style="font-size:0.7rem;font-weight:800;color:var(--green);text-align:center;margin-bottom:4px">${pose.toUpperCase()} POSE</div>
      <div class="grid-2" style="gap:6px">${cell(pA, wkA)}${cell(pB, wkB)}</div>
    </div>`;
  }).join('');

  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px">
      <div style="font-size:0.78rem;font-weight:800;color:#fff">👁️ COACH VIEW: WEEK-OVER-WEEK SIDE-BY-SIDE (Wk ${wkA} vs Wk ${wkB})</div>
      <span class="badge badge-green">Coach &amp; Challenger View</span>
    </div>
    <div class="grid-2" style="gap:8px;margin-bottom:8px;font-size:0.72rem">
      <div style="padding:8px;border-radius:8px;background:#0b110d;border:1px solid var(--border)">
        <strong style="color:var(--green)">Week ${wkA} Summary</strong>
        <div>Wt: <strong>${wA.avg_weight_kg ?? '—'} kg</strong> · Steps: <strong>${(wA.avg_steps || 0).toLocaleString()}</strong> · Cal: <strong>${wA.avg_calories || 0}</strong></div>
        <div style="color:#cbd5e1;margin-top:4px;font-size:0.69rem">${wA.challenger_comments || '<em>No write-up saved yet</em>'}</div>
      </div>
      <div style="padding:8px;border-radius:8px;background:#0b110d;border:1px solid var(--border)">
        <strong style="color:var(--green)">Week ${wkB} Summary</strong>
        <div>Wt: <strong>${wB.avg_weight_kg ?? '—'} kg</strong> · Steps: <strong>${(wB.avg_steps || 0).toLocaleString()}</strong> · Cal: <strong>${wB.avg_calories || 0}</strong></div>
        <div style="color:#cbd5e1;margin-top:4px;font-size:0.69rem">${wB.challenger_comments || '<em>No write-up saved yet</em>'}</div>
      </div>
    </div>
    <div class="grid-3" style="gap:8px">${poseRows}</div>
  `;
}

const _origLoadWeekSheet = window.loadWeekSheet;
if (typeof _origLoadWeekSheet === 'function') {
  window.loadWeekSheet = async function(weekNum) {
    await _origLoadWeekSheet(weekNum);
    renderThreePhotoSlots();
    renderWeeklySubmissionState();
    await renderWeeklyCheckinCardCanvas();
    renderCoachWowSideBySide();
  };
}

window.autoDetectTelegramChatId = async function() {
  const bot_token = document.getElementById('cfg-tg-token')?.value || '';
  const box = document.getElementById('sync-connection-report');
  if (box) box.innerHTML = '🔍 Checking your Telegram Bot for your personal Chat ID...';
  const res = await fetch('/api/challenge/telegram/detect-chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bot_token }),
  });
  const data = await res.json();
  if (data.ok) {
    const chatInput = document.getElementById('cfg-tg-chat');
    if (chatInput) chatInput.value = data.chat_id;
    if (box) box.innerHTML = `✅ Found your Telegram Chat ID: <strong>${data.chat_id}</strong> (${data.chat_name}). Click <strong>🧪 Test Send Weekly PNG to Me</strong>!`;
    showToast(`✅ Detected Telegram Chat ID: ${data.chat_id}`);
  } else {
    if (box) box.innerHTML = `<span style="color:#f87171">⚠️ ${data.error}</span>`;
    showToast(`⚠️ ${data.error}`);
  }
};

window.testTelegramToSelf = async function() {
  const bot_token = document.getElementById('cfg-tg-token')?.value || '';
  const chat_id = document.getElementById('cfg-tg-chat')?.value || '';
  if (window.renderWeeklyCheckinCardCanvas) await window.renderWeeklyCheckinCardCanvas();
  const canvas = document.getElementById('weekly-checkin-card-canvas');
  const photo_data_url = canvas ? canvas.toDataURL('image/png') : '';
  const res = await fetch('/api/challenge/telegram/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ week_num: getActiveSheetWeek(), bot_token, chat_id, photo_data_url }),
  });
  const data = await res.json();
  const box = document.getElementById('sync-connection-report');
  if (data.sent_via_api) {
    if (box) box.innerHTML = `<span style="color:#3DFF4F">✅ Sent Stylised Weekly PNG (${data.photo_sent ? 'Image + Text' : 'Text'}) to your Telegram (Chat ID: ${chat_id})!</span>`;
    showToast('✈️ Sent Weekly PNG + Summary to your Telegram!');
  } else {
    await window.downloadWeeklyCheckinPng();
    if (box) box.innerHTML = `🖼️ Downloaded Weekly PNG & copied caption! (To send automatically via Bot API, add a @BotFather token & Chat ID above.)`;
  }
};

window.triggerAppleHealthSyncModal = function() {
  if (typeof switchTab === 'function') switchTab('integrations');
  const el = document.getElementById('apple-health-bridge-panel');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  showToast('🍎 Opened Apple Health + MyFitnessPal HealthKit setup');
};

window.copyAppleHealthShortcutConfig = async function() {
  const urlInput = document.getElementById('cfg-apple-health-url');
  const endpointUrl = (urlInput && urlInput.value) || `${window.location.origin}/api/challenge/sync/apple-health`;
  const samplePayload = JSON.stringify({
    date: STATE.date,
    steps: 11500,
    sleep_hours: 7.8,
    weight_kg: 83.2,
    calories: 2150,
    protein_g: 152,
    water_l: 3.7,
    workouts: [{ type: 'TraditionalStrengthTraining', name: 'Gym Session', duration_mins: 45 }]
  }, null, 2);
  const info = `POST ${endpointUrl}\nContent-Type: application/json\n\n${samplePayload}`;
  try { await navigator.clipboard.writeText(info); } catch (e) {}
  const box = document.getElementById('sync-connection-report');
  if (box) {
    box.style.display = 'block';
    box.innerHTML = `<span style="color:#3DFF4F">📋 Copied your personal iOS Shortcut URL (<code>${endpointUrl}</code>) &amp; JSON template to clipboard!</span>`;
  }
  showToast('📋 Copied personal Apple Health iOS Shortcut URL & JSON!');
};

window.testAppleHealthSync = async function() {
  const box = document.getElementById('sync-connection-report');
  if (box) {
    box.style.display = 'block';
    box.innerHTML = '🍎 Testing Apple Health + MyFitnessPal HealthKit sync workflow...';
  }
  const res = await fetch('/api/challenge/sync/apple-health', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ simulate: true, date: STATE.date }),
  });
  const data = await res.json();
  if (data.ok) {
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    const c = data.checkin || {};
    if (box) {
      box.style.display = 'block';
      box.innerHTML = `
        <div style="color:var(--green);font-weight:800;margin-bottom:4px">🍎 Apple Health + MFP Workflow Verified (${data.date})!</div>
        <div>• <strong>Steps:</strong> ${(c.steps || 0).toLocaleString()} · <strong>Sleep:</strong> ${c.sleep_str || '7h 48m'} · <strong>Weight:</strong> ${c.weight_kg || '—'} kg</div>
        <div>• <strong>Nutrition (MFP HealthKit):</strong> ${c.calories || 0} kcal · ${c.protein_g || 0}g Protein · ${c.water_l || 0}L Water · <strong>Training:</strong> ${c.training_type || 'GYM'}</div>
      `;
    }
    showToast(`🍎 Apple Health + MFP test synced for ${data.date}!`);
  }
};

const DAILY_MOMENT_SLOTS = [
  { key: 'Breakfast', label: 'Photo 1 · Breakfast / Meal 1', icon: '🍳', tag: '#breakfast' },
  { key: 'Lunch', label: 'Photo 2 · Lunch / Meal 2', icon: '🥗', tag: '#lunch' },
  { key: 'Dinner', label: 'Photo 3 · Dinner / Snack', icon: '🍽️', tag: '#dinner' },
  { key: 'Snack', label: 'Snack', icon: '🍎', tag: '#snack' },
  { key: 'Workout / Event', label: 'Photo 4 · Workout / Steps', icon: '🏋️', tag: '#workout' },
];

const DAILY_4_PHOTO_SLOTS = [
  { key: 'Breakfast', label: 'Photo 1 · Breakfast', icon: '🍳', tag: '#breakfast' },
  { key: 'Lunch', label: 'Photo 2 · Lunch', icon: '🥗', tag: '#lunch' },
  { key: 'Dinner', label: 'Photo 3 · Dinner', icon: '🍽️', tag: '#dinner' },
  { key: 'Workout / Event', label: 'Photo 4 · Workout / Steps', icon: '🏋️', tag: '#workout' },
];

function compressImageFileToDataUrl(file, maxDim = 760, quality = 0.82) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = function(ev) {
      const img = new Image();
      img.onerror = reject;
      img.onload = function() {
        const scale = Math.min(1, maxDim / Math.max(img.width || 1, img.height || 1));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', quality));
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  });
}

window.uploadDailyMomentPhoto = async function(slotKey, event) {
  const file = event && event.target && event.target.files ? event.target.files[0] : null;
  if (!file) return;
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  try {
    showToast(`📸 Uploading ${slotKey} photo...`);
    const dataUrl = await compressImageFileToDataUrl(file);
    const res = await fetch('/api/challenge/daily-moments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: curDate,
        slot: slotKey,
        photo_data_url: dataUrl,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (!window.PROGRESS_SUMMARY) window.PROGRESS_SUMMARY = {};
      const others = (window.PROGRESS_SUMMARY.daily_moments || []).filter(m => m.date !== curDate);
      window.PROGRESS_SUMMARY.daily_moments = [...(data.moments || []), ...others];
      renderDailyJourneyMoments();
      await window.renderDailyCollageCanvas(true);
      showToast(`✅ Added ${slotKey} photo to today's 4-photo collage!`);
    }
  } catch (err) {
    showToast('⚠️ Could not upload photo — please try again.');
  }
};

window.uploadMultipleDailyPhotos = async function(event) {
  const files = event && event.target && event.target.files ? Array.from(event.target.files).slice(0, 4) : [];
  if (!files.length) return;
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const allMoments = (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || [];
  const dayMoments = allMoments.filter(m => m.date === curDate && m.photo_data_url);
  const usedSlots = new Set(dayMoments.map(m => m.slot));
  // Fill empty slots first, then overwrite in order 1..4
  const orderedSlots = [
    ...DAILY_4_PHOTO_SLOTS.map(s => s.key).filter(k => !usedSlots.has(k)),
    ...DAILY_4_PHOTO_SLOTS.map(s => s.key),
  ];

  showToast(`📸 Adding ${files.length} photo(s) to today's 4-photo collage...`);
  let latestMoments = null;
  for (let i = 0; i < files.length; i++) {
    const slotKey = orderedSlots[i] || DAILY_4_PHOTO_SLOTS[i % 4].key;
    try {
      const dataUrl = await compressImageFileToDataUrl(files[i]);
      const res = await fetch('/api/challenge/daily-moments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date: curDate,
          slot: slotKey,
          photo_data_url: dataUrl,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        latestMoments = data.moments || [];
      }
    } catch (e) {}
  }
  if (latestMoments) {
    if (!window.PROGRESS_SUMMARY) window.PROGRESS_SUMMARY = {};
    const others = (window.PROGRESS_SUMMARY.daily_moments || []).filter(m => m.date !== curDate);
    window.PROGRESS_SUMMARY.daily_moments = [...latestMoments, ...others];
  }
  if (event && event.target) event.target.value = '';
  renderDailyJourneyMoments();
  await window.renderDailyCollageCanvas(true);
  showToast(`✅ Loaded ${files.length} photo(s) into your 4-photo collage!`);
};

window.deleteDailyMomentPhoto = async function(slotKey) {
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  try {
    const res = await fetch('/api/challenge/daily-moments', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: curDate, slot: slotKey }),
    });
    const data = await res.json();
    if (data.ok) {
      if (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) {
        window.PROGRESS_SUMMARY.daily_moments = window.PROGRESS_SUMMARY.daily_moments.filter(
          m => !(m.date === curDate && m.slot === slotKey)
        );
      }
      renderDailyJourneyMoments();
      await window.renderDailyCollageCanvas(false);
      showToast(`🗑️ Removed ${slotKey} photo`);
    }
  } catch (e) {}
};

window.saveDailyMomentCaption = async function(slotKey, caption) {
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const allMoments = (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || [];
  const existing = allMoments.find(m => m.date === curDate && m.slot === slotKey) || {};
  try {
    const res = await fetch('/api/challenge/daily-moments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: curDate,
        slot: slotKey,
        caption: caption || '',
        photo_data_url: existing.photo_data_url || '',
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (!window.PROGRESS_SUMMARY) window.PROGRESS_SUMMARY = {};
      const others = (window.PROGRESS_SUMMARY.daily_moments || []).filter(m => m.date !== curDate);
      window.PROGRESS_SUMMARY.daily_moments = [...(data.moments || []), ...others];
      renderOnePagerDailyPhotosAndWhatsApp();
    }
  } catch (e) {}
};

function renderDailyJourneyMoments() {
  const grid = document.getElementById('daily-journey-moments-grid');
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const allMoments = (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || [];
  const dayMoments = allMoments.filter(m => m.date === curDate);

  if (grid) {
    grid.innerHTML = DAILY_MOMENT_SLOTS.map(s => {
      const m = dayMoments.find(x => x.slot === s.key) || {};
      const hasPhoto = Boolean(m.photo_data_url);
      return `<div style="background:var(--surface-2);border:1px ${hasPhoto ? 'solid var(--green)' : 'dashed var(--border)'};border-radius:10px;padding:0.5rem;text-align:center">
        <div style="font-size:0.72rem;font-weight:800;color:#fff;margin-bottom:4px">${s.icon} ${s.key}</div>
        <label style="cursor:pointer;display:block">
          ${hasPhoto
            ? `<img src="${m.photo_data_url}" style="width:100%;height:96px;object-fit:cover;border-radius:7px;border:1px solid rgba(61,255,79,0.35)"/>`
            : `<div style="height:96px;border-radius:7px;background:#070a08;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:var(--muted)">+ Tap to Add Pic</div>`}
          <input type="file" accept="image/*" style="display:none" onchange="uploadDailyMomentPhoto('${s.key}', event)"/>
        </label>
        <input type="text" value="${(m.caption || '').replace(/"/g, '&quot;')}" placeholder="Note (${s.tag})" style="margin-top:5px;font-size:0.68rem;padding:0.3rem 0.45rem" onchange="saveDailyMomentCaption('${s.key}', this.value)"/>
      </div>`;
    }).join('');
  }

  const strip = document.getElementById('sc-moments-strip');
  if (strip) {
    const withPics = dayMoments.filter(m => m.photo_data_url);
    strip.style.display = withPics.length ? 'grid' : 'none';
    strip.style.gridTemplateColumns = `repeat(${Math.min(5, Math.max(1, withPics.length))}, 1fr)`;
    strip.innerHTML = withPics.map(m => `<div style="text-align:center">
      <img src="${m.photo_data_url}" style="width:100%;height:68px;object-fit:cover;border-radius:6px;border:1px solid rgba(61,255,79,0.4)"/>
      <div style="font-size:0.6rem;color:var(--green);font-weight:700;margin-top:2px">${m.slot}</div>
    </div>`).join('');
  }
  renderOnePagerViews();
}

function getCurrentDailyValuesForSummary() {
  const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
  const c = ov.checkin || {};
  const prof = ov.profile || {};
  const wkInfo = ov.week_info || {};
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const dayName = getWeekdayNameForDate(curDate);
  const shortDate = getFormattedShortDate(curDate);

  const getFieldOrCheckin = (id, fallbackVal) => {
    const el = document.getElementById(id);
    if (el && el.value !== undefined && String(el.value).trim() !== '') {
      return String(el.value).trim();
    }
    return fallbackVal != null && fallbackVal !== '' && fallbackVal !== 0 ? String(fallbackVal) : '';
  };

  const stepsRaw = getFieldOrCheckin('op-steps', c.steps);
  const stepsNum = parseInt(stepsRaw || '0', 10) || 0;
  const stepTarget = Number(wkInfo.step_target || prof.step_target_wk1 || 10000);
  const calsRaw = getFieldOrCheckin('op-cals', c.calories);
  const protRaw = getFieldOrCheckin('op-prot', c.protein_g);
  const waterRaw = getFieldOrCheckin('op-water', c.water_l);
  const sleepRaw = getFieldOrCheckin(
    'op-sleep',
    c.sleep_mins && Number(c.sleep_mins) > 0
      ? (c.sleep_str || `${Math.floor(c.sleep_mins / 60)}h ${c.sleep_mins % 60}m`)
      : (c.sleep_str || '')
  );
  const trainingVal = (document.getElementById('op-training')?.value || c.training_type || 'REST').toUpperCase();
  const notesVal = (document.getElementById('op-notes')?.value ?? c.notes ?? c.class_attended ?? '').trim();
  const firstName = ((prof.client_name || 'Challenger').split(' ')[0] || 'Challenger').replace(/[^A-Za-z0-9]/g, '');

  return {
    curDate,
    dayName,
    shortDate,
    firstName,
    clientName: prof.client_name || 'Challenger',
    phaseLabel: wkInfo.phase_label || '8-Week Challenge',
    stepsNum,
    stepTarget,
    stepsDisplay: stepsNum > 0 ? stepsNum.toLocaleString() : '—',
    calsDisplay: calsRaw ? `${calsRaw} kcal` : '—',
    protDisplay: protRaw ? `${protRaw}g` : '—',
    waterDisplay: waterRaw ? `${Number(waterRaw).toFixed(2)}L` : '—',
    sleepDisplay: sleepRaw || '—',
    trainingVal,
    notesVal,
  };
}

window.buildLiveWhatsAppSummaryText = function() {
  const s = getCurrentDailyValuesForSummary();
  const stepCheck = s.stepsNum >= s.stepTarget && s.stepsNum > 0 ? '✅' : '👟';
  const trainLine = s.notesVal
    ? `🏋️ Training: ${s.trainingVal} (${s.notesVal})`
    : `🏋️ Training: ${s.trainingVal}`;

  const lines = [
    `📅 *${s.dayName} (${s.shortDate}) · CS Fitness Daily Summary*`,
    `${stepCheck} Steps: *${s.stepsDisplay}* / ${s.stepTarget.toLocaleString()}`,
    `🔥 Calories: *${s.calsDisplay}* · 💪 Protein: *${s.protDisplay}*`,
    `💧 Water: *${s.waterDisplay}* · 😴 Sleep: *${s.sleepDisplay}*`,
    trainLine,
    `#${s.firstName} #steps #macros #winTheDay #CSFitness`,
  ];
  return lines.join('\n');
};

function renderOnePagerDailyPhotosAndWhatsApp() {
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const allMoments = (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || [];
  const dayMoments = allMoments.filter(m => m.date === curDate);

  const grid4 = document.getElementById('op-daily-4photos-grid');
  const countBadge = document.getElementById('op-4photos-count-badge');
  let uploadedCount = 0;

  if (grid4) {
    grid4.innerHTML = DAILY_4_PHOTO_SLOTS.map((slot, idx) => {
      const m = dayMoments.find(x => x.slot === slot.key) || {};
      const hasPhoto = Boolean(m.photo_data_url);
      if (hasPhoto) uploadedCount++;
      return `
        <div style="background:#080c09;border:1.5px ${hasPhoto ? 'solid var(--green)' : 'dashed rgba(148,163,184,0.35)'};border-radius:12px;padding:0.45rem;position:relative">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem">
            <span style="font-size:0.72rem;font-weight:800;color:${hasPhoto ? 'var(--green)' : '#cbd5e1'}">${slot.icon} ${slot.label}</span>
            ${hasPhoto ? `<button type="button" onclick="deleteDailyMomentPhoto('${slot.key}')" title="Remove photo" style="background:rgba(248,113,113,0.18);border:1px solid rgba(248,113,113,0.45);color:#fca5a5;border-radius:6px;padding:0.05rem 0.35rem;font-size:0.65rem;cursor:pointer;font-weight:800">✕</button>` : `<span style="font-size:0.64rem;color:var(--muted)">#${idx + 1}</span>`}
          </div>
          <label style="cursor:pointer;display:block">
            ${hasPhoto
              ? `<img src="${m.photo_data_url}" alt="${slot.key}" style="width:100%;height:110px;object-fit:cover;border-radius:8px;border:1px solid rgba(61,255,79,0.4);display:block"/>`
              : `<div style="height:110px;border-radius:8px;background:rgba(255,255,255,0.02);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;color:#94a3b8;font-size:0.74rem;font-weight:700">
                   <span style="font-size:1.3rem">${slot.icon}</span>
                   <span>+ Tap to Add Photo ${idx + 1}</span>
                 </div>`}
            <input type="file" accept="image/*" style="display:none" onchange="uploadDailyMomentPhoto('${slot.key}', event)"/>
          </label>
          <input type="text" value="${(m.caption || '').replace(/"/g, '&quot;')}" placeholder="Optional caption (${slot.tag})"
                 style="margin-top:0.35rem;font-size:0.72rem;padding:0.3rem 0.45rem;border-radius:7px"
                 onchange="saveDailyMomentCaption('${slot.key}', this.value)"/>
        </div>
      `;
    }).join('');
  }

  if (countBadge) {
    countBadge.textContent = `${uploadedCount} / 4 Photos Added`;
    countBadge.className = 'badge ' + (uploadedCount === 4 ? 'badge-green' : uploadedCount > 0 ? 'badge-blue' : 'badge-amber');
  }

  const captionText = window.buildLiveWhatsAppSummaryText();
  const waBox = document.getElementById('op-wa-caption-box');
  if (waBox && document.activeElement !== waBox) {
    waBox.value = captionText;
  }
  const desktopWaBox = document.getElementById('wa-caption-box');
  if (desktopWaBox && document.activeElement !== desktopWaBox) {
    desktopWaBox.value = captionText;
  }
  const waLink = document.getElementById('op-wa-direct-link');
  if (waLink) {
    waLink.href = `https://wa.me/?text=${encodeURIComponent(captionText)}`;
  }
}

window.copyOnePagerWhatsAppSummary = async function(triggerBtn) {
  const waBox = document.getElementById('op-wa-caption-box');
  const text = (waBox && waBox.value) ? waBox.value : window.buildLiveWhatsAppSummaryText();
  const btn = window.setButtonBusy(triggerBtn || document.getElementById('op-btn-copy-wa'), '⏳ Copying...');
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    if (waBox) {
      waBox.select();
      try { document.execCommand('copy'); } catch (err) {}
    }
  }
  window.clearButtonBusy(btn, '✅ Copied for WhatsApp!');
  showToast('📋 Daily WhatsApp summary copied! Paste directly into your WhatsApp group.');
};

function loadImageElement(src) {
  return new Promise((resolve) => {
    if (!src) return resolve(null);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

function drawCoverImage(ctx, img, x, y, w, h, radius = 16) {
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, radius);
  ctx.clip();
  const imgRatio = (img.width || 1) / (img.height || 1);
  const boxRatio = w / h;
  let drawW = w;
  let drawH = h;
  let offsetX = x;
  let offsetY = y;
  if (imgRatio > boxRatio) {
    drawW = h * imgRatio;
    offsetX = x - (drawW - w) / 2;
  } else {
    drawH = w / imgRatio;
    offsetY = y - (drawH - h) / 2;
  }
  ctx.drawImage(img, offsetX, offsetY, drawW, drawH);
  ctx.restore();
}

window.renderDailyCollageCanvas = async function(showPreview = true) {
  const canvas = document.getElementById('op-daily-collage-canvas');
  if (!canvas) return null;
  const ctx = canvas.getContext('2d');
  const s = getCurrentDailyValuesForSummary();
  const curDate = s.curDate;
  const allMoments = (window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.daily_moments) || [];
  const dayMoments = allMoments.filter(m => m.date === curDate);

  // Canvas dimensions: 1080 x 1350 (4:5 Instagram / WhatsApp portrait collage)
  canvas.width = 1080;
  canvas.height = 1350;

  const bg = ctx.createLinearGradient(0, 0, 1080, 1350);
  bg.addColorStop(0, '#050806');
  bg.addColorStop(0.55, '#0b150e');
  bg.addColorStop(1, '#050806');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 1080, 1350);

  // Outer neon border
  ctx.strokeStyle = '#3DFF4F';
  ctx.lineWidth = 5;
  ctx.strokeRect(24, 24, 1032, 1302);

  // Top Header Bar
  ctx.fillStyle = '#3DFF4F';
  ctx.font = '900 28px Inter, -apple-system, sans-serif';
  ctx.fillText('CS FITNESS · 8-WEEK CHALLENGE', 56, 78);

  ctx.fillStyle = '#ffffff';
  ctx.font = '900 44px Inter, -apple-system, sans-serif';
  ctx.fillText(`${s.dayName.toUpperCase()} · ${s.shortDate.toUpperCase()}`, 56, 132);

  ctx.fillStyle = '#94a3b8';
  ctx.font = '700 24px Inter, -apple-system, sans-serif';
  ctx.fillText(`${s.clientName} · ${s.phaseLabel} · Daily 4-Photo & Stats Summary`, 56, 168);

  // 2x2 Photo Collage Grid (Y: 196 -> 846, Height: 650)
  const gridX = 56;
  const gridY = 194;
  const gap = 18;
  const cellW = Math.floor((1080 - 112 - gap) / 2); // 475
  const cellH = 312;

  for (let i = 0; i < DAILY_4_PHOTO_SLOTS.length; i++) {
    const slot = DAILY_4_PHOTO_SLOTS[i];
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = gridX + col * (cellW + gap);
    const y = gridY + row * (cellH + gap);
    const m = dayMoments.find(d => d.slot === slot.key) || {};
    const img = await loadImageElement(m.photo_data_url);

    ctx.fillStyle = '#0d1410';
    ctx.beginPath();
    ctx.roundRect(x, y, cellW, cellH, 18);
    ctx.fill();

    if (img) {
      drawCoverImage(ctx, img, x, y, cellW, cellH, 18);
    } else {
      ctx.fillStyle = '#475569';
      ctx.font = '800 28px Inter, -apple-system, sans-serif';
      ctx.fillText(`${slot.icon} ${slot.key}`, x + 32, y + cellH / 2 - 6);
      ctx.fillStyle = '#64748b';
      ctx.font = '600 20px Inter, -apple-system, sans-serif';
      ctx.fillText('No photo added for this slot', x + 32, y + cellH / 2 + 28);
    }

    ctx.strokeStyle = img ? 'rgba(61,255,79,0.75)' : 'rgba(148,163,184,0.28)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.roundRect(x, y, cellW, cellH, 18);
    ctx.stroke();

    // Label pill at bottom of each photo
    ctx.fillStyle = 'rgba(5, 8, 6, 0.82)';
    ctx.beginPath();
    ctx.roundRect(x + 12, y + cellH - 48, cellW - 24, 36, 10);
    ctx.fill();

    ctx.fillStyle = '#3DFF4F';
    ctx.font = '800 19px Inter, -apple-system, sans-serif';
    const capText = m.caption ? `${slot.key}: ${m.caption}` : slot.key;
    ctx.fillText(capText.slice(0, 38), x + 24, y + cellH - 23);
  }

  // Bottom Scoreboard Strip (Y: 856 -> 1230)
  const statsY = 856;
  const statBoxes = [
    { label: 'DAILY STEPS', value: s.stepsDisplay, sub: `Target ${s.stepTarget.toLocaleString()}`, accent: '#3DFF4F' },
    { label: 'CALORIES', value: s.calsDisplay, sub: 'Daily Nutrition', accent: '#38bdf8' },
    { label: 'PROTEIN', value: s.protDisplay, sub: 'Daily Target', accent: '#3DFF4F' },
    { label: 'WATER INTAKE', value: s.waterDisplay, sub: 'Hydration', accent: '#38bdf8' },
    { label: 'SLEEP', value: s.sleepDisplay, sub: 'Recovery', accent: '#a855f7' },
    { label: 'TRAINING', value: s.trainingVal, sub: (s.notesVal || 'Daily Session').slice(0, 24), accent: '#fbbf24' },
  ];

  const sColW = Math.floor((1080 - 112 - 32) / 3); // 3 cols x 2 rows
  const sRowH = 165;
  statBoxes.forEach((b, idx) => {
    const col = idx % 3;
    const row = Math.floor(idx / 3);
    const bx = 56 + col * (sColW + 16);
    const by = statsY + row * (sRowH + 14);

    ctx.fillStyle = '#0c130e';
    ctx.beginPath();
    ctx.roundRect(bx, by, sColW, sRowH, 16);
    ctx.fill();
    ctx.strokeStyle = 'rgba(61,255,79,0.32)';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#94a3b8';
    ctx.font = '800 18px Inter, -apple-system, sans-serif';
    ctx.fillText(b.label, bx + 20, by + 36);

    ctx.fillStyle = b.accent;
    ctx.font = '900 38px Inter, -apple-system, sans-serif';
    ctx.fillText(String(b.value).slice(0, 14), bx + 20, by + 94);

    ctx.fillStyle = '#cbd5e1';
    ctx.font = '600 18px Inter, -apple-system, sans-serif';
    ctx.fillText(String(b.sub), bx + 20, by + 136);
  });

  // Footer Hashtags
  ctx.fillStyle = '#3DFF4F';
  ctx.font = '800 22px Inter, -apple-system, sans-serif';
  ctx.fillText(`#${s.firstName}  #steps  #macros  #winTheDay  #CSFitness`, 56, 1288);

  const wrap = document.getElementById('op-collage-preview-wrap');
  if (wrap && showPreview) {
    wrap.style.display = 'block';
  }
  return canvas;
};

window.toggleDailyCollagePreview = async function(triggerBtn) {
  const wrap = document.getElementById('op-collage-preview-wrap');
  if (!wrap) return;
  const isHidden = wrap.style.display === 'none' || !wrap.style.display;
  if (isHidden) {
    const btn = window.setButtonBusy(triggerBtn, '⏳ Building Preview...');
    await window.renderDailyCollageCanvas(true);
    window.clearButtonBusy(btn, '👁️ Preview Shown');
  } else {
    wrap.style.display = 'none';
  }
};

window.downloadOrShareDailyCollagePng = async function(triggerBtn) {
  const btn = window.setButtonBusy(
    triggerBtn || document.getElementById('op-btn-collage-wa'),
    '⏳ Generating 4-Photo Collage...'
  );
  try {
    const canvas = await window.renderDailyCollageCanvas(true);
    const captionText = window.buildLiveWhatsAppSummaryText();
    try { await navigator.clipboard.writeText(captionText); } catch (e) {}

    if (!canvas) {
      window.clearButtonBusy(btn);
      return;
    }

    const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
    const fileName = `cs-fitness-daily-${curDate}.png`;

    // Try native Web Share API with image file on mobile devices if supported
    if (navigator.canShare && canvas.toBlob) {
      const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
      if (blob) {
        const file = new File([blob], fileName, { type: 'image/png' });
        if (navigator.canShare({ files: [file] })) {
          try {
            await navigator.share({
              files: [file],
              title: `CS Fitness Daily Summary (${curDate})`,
              text: captionText,
            });
            window.clearButtonBusy(btn, '✅ Shared!');
            showToast('✅ Shared 4-Photo Collage & copied WhatsApp text!');
            return;
          } catch (shareErr) {
            // Fall through to standard PNG download if user cancels share sheet
          }
        }
      }
    }

    const link = document.createElement('a');
    link.download = fileName;
    link.href = canvas.toDataURL('image/png');
    link.click();
    window.clearButtonBusy(btn, '✅ Collage Saved!');
    showToast('🖼️ Saved 4-Photo Collage PNG + copied WhatsApp summary text to clipboard!');
  } catch (err) {
    window.clearButtonBusy(btn);
    showToast('⚠️ Could not generate collage image.');
  }
};

function wireOnePagerLiveSummaryInputs() {
  if (window._opLiveInputsWired) return;
  const ids = ['op-steps', 'op-cals', 'op-prot', 'op-water', 'op-sleep', 'op-notes'];
  let foundAny = false;
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el && !el.hasAttribute('data-wa-wired')) {
      foundAny = true;
      el.setAttribute('data-wa-wired', '1');
      el.addEventListener('input', () => {
        const txt = window.buildLiveWhatsAppSummaryText();
        const waBox = document.getElementById('op-wa-caption-box');
        if (waBox && document.activeElement !== waBox) waBox.value = txt;
        const waLink = document.getElementById('op-wa-direct-link');
        if (waLink) waLink.href = `https://wa.me/?text=${encodeURIComponent(txt)}`;
      });
    }
  });
  if (foundAny) window._opLiveInputsWired = true;
}

function getWeekdayNameForDate(dateStr) {
  try {
    const dt = new Date((dateStr || new Date().toISOString().slice(0, 10)) + 'T12:00:00');
    return dt.toLocaleDateString('en-GB', { weekday: 'long' });
  } catch (e) {
    return 'Today';
  }
}

function getFormattedShortDate(dateStr) {
  try {
    const dt = new Date((dateStr || new Date().toISOString().slice(0, 10)) + 'T12:00:00');
    return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch (e) {
    return dateStr || '';
  }
}

// ── MULTI-LAYER PERSISTENCE VAULT (Survives Ephemeral Container Restarts) ──
function getActiveVaultProfileId() {
  const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
  return Number((ov.profile && ov.profile.id) || 1);
}

function getCheckinsVaultKey(pid) {
  return `cs_fitness_checkins_vault_p${pid || getActiveVaultProfileId()}`;
}

function getGarminVaultKey(pid) {
  return `cs_fitness_garmin_auth_p${pid || getActiveVaultProfileId()}`;
}

function getDraftVaultKey(dateStr, pid) {
  return `cs_fitness_draft_p${pid || getActiveVaultProfileId()}_${dateStr}`;
}

window.getBrowserGarminVault = function(pid) {
  try {
    const raw = localStorage.getItem(getGarminVaultKey(pid));
    const parsed = raw ? JSON.parse(raw) : {};
    const ovIntg = (typeof STATE !== 'undefined' && STATE.overview && STATE.overview.integrations) || {};
    return {
      garmin_email: parsed.garmin_email || ovIntg.garmin_email || '',
      garmin_password_b64: parsed.garmin_password_b64 || ovIntg.garmin_password_b64 || '',
      garmin_token_dump: parsed.garmin_token_dump || ovIntg.garmin_token_dump || '',
      garmin_last_sync: parsed.garmin_last_sync || ovIntg.garmin_last_sync || '',
      garmin_connected: parsed.garmin_connected || ovIntg.garmin_connected || 0,
    };
  } catch (e) {
    return {};
  }
};

window.saveBrowserGarminVault = function(data, pid) {
  if (!data || typeof data !== 'object') return;
  try {
    const curr = window.getBrowserGarminVault(pid);
    const merged = {
      garmin_email: data.garmin_email || curr.garmin_email || '',
      garmin_password_b64: data.garmin_password_b64 || curr.garmin_password_b64 || '',
      garmin_token_dump: data.garmin_token_dump || curr.garmin_token_dump || '',
      garmin_last_sync: data.garmin_last_sync || curr.garmin_last_sync || '',
      garmin_connected: data.garmin_connected != null ? data.garmin_connected : (curr.garmin_connected || 0),
      updated_at: new Date().toISOString(),
    };
    localStorage.setItem(getGarminVaultKey(pid), JSON.stringify(merged));
  } catch (e) {}
};

window.getBrowserCheckinsVault = function(pid) {
  try {
    const raw = localStorage.getItem(getCheckinsVaultKey(pid));
    return raw ? JSON.parse(raw) : { profile_id: pid || getActiveVaultProfileId(), daily_checkins: [], workout_logs: [], weekly_submissions: [] };
  } catch (e) {
    return { profile_id: pid || getActiveVaultProfileId(), daily_checkins: [], workout_logs: [], weekly_submissions: [] };
  }
};

function hasMeaningfulCheckinData(c) {
  if (!c) return false;
  return Boolean(
    (c.weight_kg != null && Number(c.weight_kg) > 0) ||
    Number(c.steps || 0) > 0 ||
    Number(c.calories || 0) > 0 ||
    Number(c.protein_g || 0) > 0 ||
    Number(c.water_l || 0) > 0 ||
    Number(c.sleep_mins || 0) > 0 ||
    (c.sleep_str && String(c.sleep_str).trim()) ||
    (c.sleep && String(c.sleep).trim()) ||
    (c.notes && String(c.notes).trim())
  );
}

window.recordCheckinInBrowserVault = function(row, pid) {
  if (!row || !row.date) return;
  try {
    const targetPid = pid || getActiveVaultProfileId();
    const vault = window.getBrowserCheckinsVault(targetPid);
    const list = Array.isArray(vault.daily_checkins) ? vault.daily_checkins : [];
    const dStr = String(row.date).slice(0, 10);
    const idx = list.findIndex(x => String(x.date).slice(0, 10) === dStr);
    const existing = idx >= 0 ? list[idx] : { date: dStr, profile_id: targetPid };
    const merged = Object.assign({}, existing);
    Object.keys(row).forEach(k => {
      const v = row[k];
      if (v !== undefined && v !== null && v !== '') {
        merged[k] = v;
      }
    });
    if (row.sleep && !merged.sleep_str) {
      merged.sleep_str = String(row.sleep);
    }
    if (idx >= 0) {
      list[idx] = merged;
    } else {
      list.push(merged);
    }
    vault.daily_checkins = list;
    vault.updated_at = new Date().toISOString();
    localStorage.setItem(getCheckinsVaultKey(targetPid), JSON.stringify(vault));
    const badge = document.getElementById('op-persistence-badge');
    if (badge) {
      badge.style.color = 'var(--green)';
      badge.textContent = '🔒 Saved to Device & Cloud ✓';
    }
  } catch (e) {}
};

window.pullServerBackupIntoBrowserVault = async function() {
  try {
    const res = await fetch('/api/challenge/backup/export');
    const data = await res.json();
    if (!data || !data.ok) return;
    const pid = Number(data.profile_id || getActiveVaultProfileId());
    if (data.integrations) {
      window.saveBrowserGarminVault(data.integrations, pid);
    }
    const localVault = window.getBrowserCheckinsVault(pid);
    const byDate = {};
    (localVault.daily_checkins || []).forEach(c => {
      if (c && c.date) byDate[String(c.date).slice(0, 10)] = Object.assign({}, c);
    });
    (data.daily_checkins || []).forEach(sc => {
      if (!sc || !sc.date) return;
      const d = String(sc.date).slice(0, 10);
      const prev = byDate[d] || {};
      const merged = Object.assign({}, prev);
      Object.keys(sc).forEach(k => {
        const sv = sc[k];
        if (sv !== null && sv !== undefined && sv !== '' && sv !== 0) {
          merged[k] = sv;
        } else if (merged[k] === undefined) {
          merged[k] = sv;
        }
      });
      byDate[d] = merged;
    });
    const nextVault = {
      profile_id: pid,
      updated_at: new Date().toISOString(),
      profile: data.profile || localVault.profile || {},
      user_account: data.user_account || localVault.user_account || {},
      daily_checkins: Object.values(byDate).sort((a, b) => String(a.date).localeCompare(String(b.date))),
      workout_logs: (data.workout_logs && data.workout_logs.length) ? data.workout_logs : (localVault.workout_logs || []),
      weekly_submissions: (data.weekly_submissions && data.weekly_submissions.length) ? data.weekly_submissions : (localVault.weekly_submissions || []),
      daily_activities: (data.daily_activities && data.daily_activities.length) ? data.daily_activities : (localVault.daily_activities || []),
    };
    localStorage.setItem(getCheckinsVaultKey(pid), JSON.stringify(nextVault));
  } catch (e) {}
};

async function ensureServerRehydratedFromBrowserVault() {
  try {
    const pid = getActiveVaultProfileId();
    const localVault = window.getBrowserCheckinsVault(pid);
    const garminVault = window.getBrowserGarminVault(pid);
    const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
    const serverIntg = ov.integrations || {};

    // Check if localVault has check-ins or Garmin auth that the server lost after a container restart
    const localMeaningful = (localVault.daily_checkins || []).filter(hasMeaningfulCheckinData);
    const needsGarminRestore = Boolean(
      (garminVault.garmin_email && !serverIntg.garmin_email) ||
      (garminVault.garmin_password_b64 && !serverIntg.garmin_password_set) ||
      (garminVault.garmin_token_dump && !serverIntg.garmin_connected)
    );

    let needsCheckinRestore = false;
    if (localMeaningful.length > 0) {
      try {
        const cRes = await fetch('/api/challenge/checkins');
        const serverRows = await cRes.json();
        const serverMap = {};
        (Array.isArray(serverRows) ? serverRows : []).forEach(r => {
          if (r && r.date) serverMap[String(r.date).slice(0, 10)] = r;
        });
        for (const lc of localMeaningful) {
          const d = String(lc.date).slice(0, 10);
          const sc = serverMap[d];
          if (!sc || !hasMeaningfulCheckinData(sc)) {
            needsCheckinRestore = true;
            break;
          }
          if (
            (lc.weight_kg && !sc.weight_kg) ||
            (Number(lc.steps || 0) > Number(sc.steps || 0)) ||
            (Number(lc.calories || 0) > Number(sc.calories || 0)) ||
            (Number(lc.protein_g || 0) > Number(sc.protein_g || 0)) ||
            (Number(lc.water_l || 0) > Number(sc.water_l || 0))
          ) {
            needsCheckinRestore = true;
            break;
          }
        }
      } catch (e) {}
    }

    if (needsGarminRestore || needsCheckinRestore) {
      const importPayload = {
        profile_id: pid,
        profile: localVault.profile || ov.profile || {},
        user_account: localVault.user_account || {},
        integrations: garminVault,
        daily_checkins: localMeaningful,
        workout_logs: localVault.workout_logs || [],
        weekly_submissions: localVault.weekly_submissions || [],
        daily_activities: localVault.daily_activities || [],
      };
      await fetch('/api/challenge/backup/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(importPayload),
      });
      if (typeof loadOverview === 'function') {
        await loadOverview(STATE.date);
      }
    } else if (serverIntg.garmin_email || serverIntg.garmin_password_b64 || serverIntg.garmin_token_dump) {
      window.saveBrowserGarminVault(serverIntg, pid);
    }
  } catch (e) {
    console.warn('Vault rehydration check error:', e);
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    ensureServerRehydratedFromBrowserVault().then(() => {
      renderOnePagerViews();
    });
  }
});

let _onePagerAutoSaveTimer = null;
window.scheduleOnePagerAutoSave = function() {
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const wtVal = document.getElementById('op-weight')?.value?.trim() || '';
  const stepsVal = document.getElementById('op-steps')?.value?.trim() || '';
  const calsVal = document.getElementById('op-cals')?.value?.trim() || '';
  const protVal = document.getElementById('op-prot')?.value?.trim() || '';
  const waterVal = document.getElementById('op-water')?.value?.trim() || '';
  const sleepVal = document.getElementById('op-sleep')?.value?.trim() || '';
  const trainVal = document.getElementById('op-training')?.value || 'REST';
  const notesVal = document.getElementById('op-notes')?.value || '';

  const draft = {
    date: curDate,
    training_type: trainVal,
    notes: notesVal,
  };
  if (wtVal !== '') draft.weight_kg = parseFloat(wtVal);
  if (stepsVal !== '') draft.steps = parseInt(stepsVal, 10);
  if (calsVal !== '') draft.calories = parseInt(calsVal, 10);
  if (protVal !== '') draft.protein_g = parseInt(protVal, 10);
  if (waterVal !== '') draft.water_l = parseFloat(waterVal);
  if (sleepVal !== '') draft.sleep = sleepVal;

  // Save immediately to Browser Vault so closing the phone tab never loses typed numbers
  window.recordCheckinInBrowserVault(draft);
  try {
    localStorage.setItem(getDraftVaultKey(curDate), JSON.stringify(draft));
  } catch (e) {}

  const badge = document.getElementById('op-persistence-badge');
  if (badge) {
    badge.style.color = '#38bdf8';
    badge.textContent = '💾 Auto-saving...';
  }

  if (_onePagerAutoSaveTimer) clearTimeout(_onePagerAutoSaveTimer);
  _onePagerAutoSaveTimer = setTimeout(async () => {
    try {
      await fetch('/api/challenge/checkins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      try {
        localStorage.removeItem(getDraftVaultKey(curDate));
      } catch (e) {}
      if (badge) {
        badge.style.color = 'var(--green)';
        badge.textContent = '🔒 Auto-Saved ✓';
      }
      renderMobileDailyWeekStrip();
    } catch (e) {
      if (badge) {
        badge.style.color = '#fbbf24';
        badge.textContent = '📱 Saved on Device (Offline)';
      }
    }
  }, 900);
};

window.selectOnePagerTraining = function(val, triggerSave) {
  const trainVal = val || 'REST';
  const hidden = document.getElementById('op-training');
  const prevVal = hidden ? hidden.value : 'REST';
  if (hidden) hidden.value = trainVal;
  document.querySelectorAll('#op-training-btns .op-train-btn').forEach(btn => {
    const bVal = btn.getAttribute('data-train');
    if (bVal === trainVal) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
  if (typeof window.buildLiveWhatsAppSummaryText === 'function') {
    const txt = window.buildLiveWhatsAppSummaryText();
    const waBox = document.getElementById('op-wa-caption-box');
    if (waBox && document.activeElement !== waBox) waBox.value = txt;
    const waLink = document.getElementById('op-wa-direct-link');
    if (waLink) waLink.href = `https://wa.me/?text=${encodeURIComponent(txt)}`;
  }
  if (triggerSave && prevVal !== trainVal && typeof window.scheduleOnePagerAutoSave === 'function') {
    window.scheduleOnePagerAutoSave();
  }
};

window.toggleMobileGarminDrawer = function(forceOpen) {
  const drawer = document.getElementById('op-garmin-connect-drawer');
  if (!drawer) return;
  const shouldOpen = forceOpen !== undefined ? Boolean(forceOpen) : (drawer.style.display === 'none' || !drawer.style.display);
  drawer.style.display = shouldOpen ? 'block' : 'none';
  if (shouldOpen) {
    const gv = window.getBrowserGarminVault();
    const emailInput = document.getElementById('op-garmin-email');
    if (emailInput && !emailInput.value) {
      emailInput.value = gv.garmin_email || '';
    }
  }
};

window.saveAndSyncMobileGarmin = async function() {
  const emailEl = document.getElementById('op-garmin-email');
  const passEl = document.getElementById('op-garmin-password');
  const email = (emailEl?.value || '').trim();
  const password = passEl?.value || '';
  if (!email) {
    showToast('⚠️ Enter your Garmin Connect email first.');
    if (emailEl) emailEl.focus();
    return;
  }
  const gv = window.getBrowserGarminVault();
  const passB64 = password ? btoa(unescape(encodeURIComponent(password))) : (gv.garmin_password_b64 || '');
  window.saveBrowserGarminVault({
    garmin_email: email,
    garmin_password_b64: passB64,
  });

  const btn = window.setButtonBusy(document.getElementById('op-garmin-save-sync-btn'), '⏳ Saving & Syncing Garmin...');
  try {
    const res = await fetch('/api/challenge/sync/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: STATE.date,
        garmin_email: email,
        garmin_password: password,
        garmin_password_b64: passB64,
        garmin_token_dump: gv.garmin_token_dump || '',
      }),
    });
    const data = await res.json();
    if (data.integrations) {
      window.saveBrowserGarminVault(data.integrations);
    }
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    renderOnePagerViews();
    window.clearButtonBusy(btn, '✅ Garmin Saved & Synced!');
    window.toggleMobileGarminDrawer(false);
    showToast(data.garmin_status || '✅ Garmin login saved & synced!');
  } catch (e) {
    window.clearButtonBusy(btn);
    showToast('⚠️ Could not reach Garmin sync service.');
  }
};

window.triggerMobileGarminSync = async function() {
  const btn = window.setButtonBusy(document.getElementById('op-btn-sync-garmin'), '⏳ Syncing with Garmin...');
  const statusEl = document.getElementById('op-sync-status');
  if (statusEl) {
    statusEl.style.color = '#38bdf8';
    statusEl.textContent = 'Connecting to Garmin Connect...';
  }
  try {
    const gv = window.getBrowserGarminVault();
    const drawerEmail = (document.getElementById('op-garmin-email')?.value || '').trim();
    const drawerPass = document.getElementById('op-garmin-password')?.value || '';
    const res = await fetch('/api/challenge/sync/live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: STATE.date,
        garmin_email: drawerEmail || gv.garmin_email || '',
        garmin_password: drawerPass || '',
        garmin_password_b64: drawerPass ? btoa(unescape(encodeURIComponent(drawerPass))) : (gv.garmin_password_b64 || ''),
        garmin_token_dump: gv.garmin_token_dump || '',
      }),
    });
    const data = await res.json();
    if (data.integrations) {
      window.saveBrowserGarminVault(data.integrations);
    }
    if (data.checkin) {
      window.recordCheckinInBrowserVault(data.checkin);
    }
    await loadOverview(STATE.date);
    await refreshProgressSummary();
    renderOnePagerViews();
    const msg = (data.messages && data.messages.join(' · ')) || 'Garmin sync completed';
    if (data.ok) {
      if (statusEl) {
        statusEl.style.color = 'var(--green)';
        statusEl.textContent = `✅ ${msg}`;
      }
      window.clearButtonBusy(btn, '✅ Garmin Synced!');
      showToast(`⌚ ${msg}`);
    } else {
      if (data.needs_password || data.needs_setup) {
        window.toggleMobileGarminDrawer(true);
      }
      if (statusEl) {
        statusEl.style.color = '#fbbf24';
        statusEl.innerHTML = `ℹ️ ${msg} · <a href="#" onclick="toggleMobileGarminDrawer(true);return false;" style="color:var(--green);font-weight:800">Enter Garmin Login Below</a>`;
      }
      window.clearButtonBusy(btn);
      showToast(`ℹ️ ${msg}`);
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.color = '#f87171';
      statusEl.textContent = 'Could not reach Garmin sync service.';
    }
    window.clearButtonBusy(btn);
  }
};

function renderMobileDailyWeekStrip() {
  const stripEl = document.getElementById('op-daily-week-strip');
  if (!stripEl) return;
  const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
  const sheet = ov.current_week_sheet || {};
  const rows = sheet.rows || [];
  const vault = window.getBrowserCheckinsVault();
  const vaultByDate = {};
  (vault.daily_checkins || []).forEach(c => {
    if (c && c.date) vaultByDate[String(c.date).slice(0, 10)] = c;
  });

  if (!rows.length) {
    stripEl.innerHTML = '';
    return;
  }
  const titleEl = document.getElementById('op-week-strip-title');
  const loggedCnt = rows.filter(r => hasMeaningfulCheckinData(r) || hasMeaningfulCheckinData(vaultByDate[r.date])).length;
  if (titleEl) {
    titleEl.textContent = `${sheet.label || 'THIS WEEK'} · ${loggedCnt}/7 DAYS SAVED`;
  }

  stripEl.innerHTML = rows.map(r => {
    const vc = vaultByDate[r.date] || {};
    const wt = r.weight_kg || vc.weight_kg;
    const st = r.steps || vc.steps;
    const hasData = hasMeaningfulCheckinData(r) || hasMeaningfulCheckinData(vc);
    const isSelected = r.date === STATE.date;
    const shortDay = r.day_short || (r.day_name || '').slice(0, 3) || r.date.slice(8, 10);
    const subTxt = wt ? `${Number(wt).toFixed(1)}k` : (st ? `${Math.round(Number(st) / 1000)}k` : (hasData ? '✓' : '·'));
    return `<button type="button" onclick="loadOverview('${r.date}')" style="padding:0.32rem 0.1rem;border-radius:8px;cursor:pointer;background:${isSelected ? 'rgba(61,255,79,0.22)' : (hasData ? 'rgba(61,255,79,0.08)' : 'var(--surface-2)')};border:1.5px solid ${isSelected ? 'var(--green)' : (hasData ? 'rgba(61,255,79,0.42)' : 'var(--border)')};color:#fff;text-align:center">
      <div style="font-size:0.62rem;font-weight:800;color:${hasData ? 'var(--green)' : '#94a3b8'}">${shortDay}</div>
      <div style="font-size:0.68rem;font-weight:900;margin-top:1px;color:${hasData ? '#fff' : 'var(--muted)'}">${hasData ? '✓ ' + subTxt : '·'}</div>
    </button>`;
  }).join('');
}

function renderOnePagerViews() {
  const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
  const serverC = ov.checkin || {};
  const prof = ov.profile || {};
  const intg = Object.assign({}, window.getBrowserGarminVault(), ov.integrations || {});
  const wkInfo = ov.week_info || {};
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const dayName = getWeekdayNameForDate(curDate);

  // Merge server check-in with local browser vault + any unsaved draft for curDate so data never blanks out
  const vault = window.getBrowserCheckinsVault();
  const vaultRow = (vault.daily_checkins || []).find(x => String(x.date).slice(0, 10) === curDate) || {};
  let draftRow = {};
  try {
    const rawDraft = localStorage.getItem(getDraftVaultKey(curDate));
    if (rawDraft) draftRow = JSON.parse(rawDraft);
  } catch (e) {}
  const c = Object.assign({}, vaultRow, serverC);
  Object.keys(vaultRow).forEach(k => {
    if ((c[k] === null || c[k] === undefined || c[k] === '' || c[k] === 0) && vaultRow[k]) {
      c[k] = vaultRow[k];
    }
  });
  Object.keys(draftRow).forEach(k => {
    if (draftRow[k] !== undefined && draftRow[k] !== null && draftRow[k] !== '') {
      c[k] = draftRow[k];
    }
  });
  if (hasMeaningfulCheckinData(serverC)) {
    window.recordCheckinInBrowserVault(serverC);
  }

  const clientNameEl = document.getElementById('op-client-name');
  if (clientNameEl && prof.client_name) {
    clientNameEl.textContent = `${prof.client_name.toUpperCase()} · DAILY`;
  }
  const wkBadgeEl = document.getElementById('op-week-badge');
  if (wkBadgeEl) {
    wkBadgeEl.textContent = wkInfo.phase_label || '8-Week Challenge';
  }
  const adminBtn = document.getElementById('op-admin-btn');
  if (adminBtn) {
    adminBtn.style.display = ov.is_admin ? 'inline-flex' : 'none';
  }

  const dayHeading = document.getElementById('op-weekday-heading');
  if (dayHeading) dayHeading.textContent = dayName;
  const dLbl = document.getElementById('op-date-lbl');
  if (dLbl) dLbl.textContent = getFormattedShortDate(curDate);

  const submitBtn = document.getElementById('op-submit-btn');
  if (submitBtn && !submitBtn.classList.contains('btn-loading')) {
    submitBtn.textContent = `✅ Submit ${dayName}`;
  }

  const saveBanner = document.getElementById('op-save-banner');
  if (saveBanner && saveBanner.getAttribute('data-saved-date') !== curDate) {
    saveBanner.style.display = 'none';
  }

  const emailEl = document.getElementById('op-garmin-email');
  if (emailEl && !emailEl.value && intg.garmin_email) {
    emailEl.value = intg.garmin_email;
  }

  const syncStatus = document.getElementById('op-sync-status');
  if (syncStatus && !syncStatus.textContent.startsWith('⏳')) {
    if (intg.garmin_last_sync) {
      syncStatus.style.color = '#94a3b8';
      syncStatus.textContent = `✅ Garmin linked (${intg.garmin_email || 'Connected'}) · Last sync: ${intg.garmin_last_sync}`;
    } else if (intg.garmin_email) {
      syncStatus.style.color = '#94a3b8';
      syncStatus.textContent = `⌚ Garmin linked (${intg.garmin_email}) · Tap above to pull today's stats`;
    } else {
      syncStatus.style.color = 'var(--muted)';
      syncStatus.innerHTML = `Tap <a href="#" onclick="toggleMobileGarminDrawer(true);return false;" style="color:var(--green);font-weight:700">🔑 Garmin Login</a> once to save your Garmin account on this device`;
    }
  }

  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) {
      el.value = v ?? '';
      el.placeholder = '';
    }
  };
  const hasMorningWt = c.weight_kg != null && Number(c.weight_kg) > 0;
  setVal('op-weight', hasMorningWt ? c.weight_kg : '');
  setVal('op-steps', c.steps && Number(c.steps) > 0 ? c.steps : '');
  setVal('op-cals', c.calories && Number(c.calories) > 0 ? c.calories : '');
  setVal('op-prot', c.protein_g && Number(c.protein_g) > 0 ? c.protein_g : '');
  setVal('op-water', c.water_l && Number(c.water_l) > 0 ? c.water_l : '');
  setVal('op-sleep', c.sleep_mins && Number(c.sleep_mins) > 0 ? (c.sleep_str || `${Math.floor(c.sleep_mins / 60)}h ${c.sleep_mins % 60}m`) : (c.sleep_str || c.sleep || ''));
  window.selectOnePagerTraining(c.training_type || 'REST', false);
  setVal('op-notes', c.notes || c.class_attended || '');

  const wtBadge = document.getElementById('op-morning-weight-badge');
  const wtSub = document.getElementById('op-morning-weight-sub');
  const rollPill = document.getElementById('op-rolling-wt-pill');
  const rollWt = ov.rolling_7d_weight_kg || prof.start_weight_kg;
  if (rollPill && rollWt) {
    rollPill.textContent = `7-Day Avg: ${Number(rollWt).toFixed(1)} kg`;
  }
  if (wtBadge) {
    wtBadge.textContent = hasMorningWt ? `✅ Logged ${Number(c.weight_kg).toFixed(1)} kg` : 'Fasted AM';
    wtBadge.className = 'badge ' + (hasMorningWt ? 'badge-green' : 'badge-blue');
  }
  if (wtSub) {
    wtSub.textContent = hasMorningWt
      ? `✅ Morning weight saved (${Number(c.weight_kg).toFixed(1)} kg${c.weigh_time ? ' · ' + c.weigh_time : ''}). End-of-day stats can be synced & submitted tonight.`
      : 'Log your scale weight first thing in the morning — End-of-Day stats can be synced & submitted tonight.';
    wtSub.style.color = hasMorningWt ? 'var(--green)' : '#94a3b8';
  }

  renderMobileDailyWeekStrip();
  wireOnePagerLiveSummaryInputs();
  renderOnePagerDailyPhotosAndWhatsApp();
  renderOnePagerWeekly();
}

window.saveMorningWeightOnly = async function(weightInputId, timeInputId) {
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const wEl = document.getElementById(weightInputId || 'op-weight') || document.getElementById('in-weight');
  const tEl = timeInputId ? document.getElementById(timeInputId) : document.getElementById('in-weigh-time');
  const rawVal = wEl ? wEl.value.trim() : '';
  const numVal = parseFloat(rawVal);
  if (!rawVal || isNaN(numVal) || numVal <= 0) {
    showToast('⚠️ Enter your morning weight (kg) first.');
    if (wEl) wEl.focus();
    return;
  }
  const now = new Date();
  const defaultTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  const weighTime = (tEl && tEl.value) ? tEl.value : defaultTime;
  const saveBtn = window.setButtonBusy(document.getElementById('op-save-weight-btn'), '⏳ Saving...');
  try {
    await window.postCheckinUpdate(
      { date: curDate, weight_kg: numVal, weigh_time: weighTime },
      `⚖️ Morning weight saved (${numVal.toFixed(1)} kg)`
    );
    await refreshProgressSummary();
    renderOnePagerViews();
    window.clearButtonBusy(saveBtn, `✅ Saved ${numVal.toFixed(1)} kg`);
  } catch (e) {
    window.clearButtonBusy(saveBtn);
  }
};

function renderOnePagerWeekly() {
  const ov = (typeof STATE !== 'undefined' && STATE.overview) || {};
  const sheet = ov.current_week_sheet || {};
  const avgs = sheet.averages || {};
  const rows = sheet.rows || [];
  const wk = getActiveSheetWeek();
  const sel = document.getElementById('op-week-select');
  if (sel) sel.value = String(wk);
  const wkObj = ((window.PROGRESS_SUMMARY && window.PROGRESS_SUMMARY.weeks) || []).find(w => Number(w.week_num) === wk) || {};

  const avgWt = avgs.avg_weight_kg || wkObj.avg_weight_kg;
  const avgSteps = avgs.avg_steps ?? wkObj.avg_steps ?? 0;
  const avgCals = avgs.avg_calories ?? wkObj.avg_calories ?? 0;
  const avgProt = avgs.avg_protein_g ?? wkObj.avg_protein_g ?? 0;
  const daysLogged = avgs.days_logged ?? wkObj.days_logged ?? 0;

  const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  setTxt('op-wk-wt', avgWt ? `${Number(avgWt).toFixed(1)}kg` : '—');
  setTxt('op-wk-steps', Number(avgSteps).toLocaleString());
  setTxt('op-wk-cals', String(avgCals));
  setTxt('op-wk-prot', `${avgProt}g`);
  setTxt('op-rollup-days-badge', `${daysLogged} / 7 Days Logged`);

  const stripEl = document.getElementById('op-weekly-days-strip');
  if (stripEl && rows.length) {
    stripEl.innerHTML = rows.map(r => {
      const hasData = Boolean(r.weight_kg || r.steps || r.calories || r.protein_g || (r.notes && r.notes.trim()));
      const isSelected = r.date === STATE.date;
      const shortDay = r.day_short || (r.day_name || '').slice(0, 3);
      return `<button type="button" onclick="loadOverview('${r.date}')" style="padding:0.35rem 0.15rem;border-radius:8px;cursor:pointer;background:${isSelected ? 'rgba(61,255,79,0.22)' : (hasData ? 'rgba(61,255,79,0.08)' : 'var(--surface-2)')};border:1.5px solid ${isSelected ? 'var(--green)' : (hasData ? 'rgba(61,255,79,0.4)' : 'var(--border)')};color:#fff;text-align:center">
        <div style="font-size:0.65rem;font-weight:800;color:${hasData ? 'var(--green)' : 'var(--muted)'}">${shortDay}</div>
        <div style="font-size:0.75rem;font-weight:900;margin-top:1px">${hasData ? '✓' : '·'}</div>
      </button>`;
    }).join('');
  }
}

window.saveOnePagerDaily = async function(withPng) {
  if (_onePagerAutoSaveTimer) {
    clearTimeout(_onePagerAutoSaveTimer);
    _onePagerAutoSaveTimer = null;
  }
  const curDate = (typeof STATE !== 'undefined' && STATE.date) || new Date().toISOString().slice(0, 10);
  const dayName = getWeekdayNameForDate(curDate);
  const submitBtn = window.setButtonBusy(document.getElementById('op-submit-btn'), `⏳ Saving ${dayName}...`);
  try {
    try { localStorage.removeItem(getDraftVaultKey(curDate)); } catch (e) {}
    const wtVal = document.getElementById('op-weight')?.value?.trim() || '';
    const stepsVal = document.getElementById('op-steps')?.value?.trim() || '';
    const calsVal = document.getElementById('op-cals')?.value?.trim() || '';
    const protVal = document.getElementById('op-prot')?.value?.trim() || '';
    const waterVal = document.getElementById('op-water')?.value?.trim() || '';
    const sleepVal = document.getElementById('op-sleep')?.value?.trim() || '';
    const payload = {
      date: curDate,
      training_type: document.getElementById('op-training')?.value || 'REST',
      notes: document.getElementById('op-notes')?.value || '',
    };
    if (wtVal !== '') payload.weight_kg = parseFloat(wtVal);
    if (stepsVal !== '') payload.steps = parseInt(stepsVal, 10);
    if (calsVal !== '') payload.calories = parseInt(calsVal, 10);
    if (protVal !== '') payload.protein_g = parseInt(protVal, 10);
    if (waterVal !== '') payload.water_l = parseFloat(waterVal);
    if (sleepVal !== '') payload.sleep = sleepVal;
    await window.postCheckinUpdate(payload, `${dayName} saved`);
    await refreshProgressSummary();
    renderOnePagerViews();

    const banner = document.getElementById('op-save-banner');
    const bannerTitle = document.getElementById('op-save-banner-title');
    const bannerSub = document.getElementById('op-save-banner-sub');
    if (banner) {
      banner.setAttribute('data-saved-date', curDate);
      banner.style.display = 'block';
    }
    if (bannerTitle) {
      bannerTitle.textContent = `✅ ${dayName} saved`;
    }
    const sheet = (STATE.overview && STATE.overview.current_week_sheet) || {};
    const daysLogged = (sheet.averages && sheet.averages.days_logged) || 1;
    if (bannerSub) {
      bannerSub.textContent = `Your ${dayName} stats are saved and collated into your Weekly Round-Up below (${daysLogged}/7 days logged this week).`;
    }
    window.clearButtonBusy(submitBtn, `✅ ${dayName} saved!`);
    if (withPng) await window.downloadInstagramScoreboardPng();
  } catch (err) {
    window.clearButtonBusy(submitBtn);
  }
};

window.changeOnePagerWeek = async function(val) {
  const ciSel = document.getElementById('ci-week-select');
  if (ciSel) ciSel.value = String(val);
  if (typeof window.loadWeekSheet === 'function') await window.loadWeekSheet(val);
  renderOnePagerWeekly();
};

window.saveOnePagerWeekly = async function(action) {
  const cm = document.getElementById('op-wk-comments')?.value || '';
  const wkCm = document.getElementById('wk-challenger-comments');
  if (wkCm) wkCm.value = cm;
  await window.submitWeeklyCheckinInApp();
  if (action === 'png') await window.downloadWeeklyCheckinPng();
  if (action === 'tg') await window.sendWeeklyTelegram();
};

window.openDesktopTab = function(tabName) {
  window.setOnePagerMode('full');
  if (typeof window.switchTab === 'function') {
    window.switchTab(tabName || 'checkin');
  }
  const bCheckin = document.getElementById('btn-mode-checkin-desk');
  const bSettings = document.getElementById('btn-mode-settings-desk');
  const bDaily = document.getElementById('btn-mode-daily1p');
  if (bDaily) bDaily.className = 'btn btn-sm';
  if (bCheckin) bCheckin.className = (tabName === 'checkin') ? 'btn btn-green btn-sm' : 'btn btn-sm';
  if (bSettings) bSettings.className = (tabName === 'integrations') ? 'btn btn-green btn-sm' : 'btn btn-sm';
};

window.setOnePagerMode = function(mode) {
  const dView = document.getElementById('onepager-daily-view');
  const wView = document.getElementById('onepager-weekly-view');
  const topHeader = document.querySelector('.top-header');
  const weekStrip = document.getElementById('hdr-week-strip');
  const modeBar = document.getElementById('mobile-onepager-bar');
  const tabs = document.getElementById('main-tabs');
  const panels = document.querySelectorAll('.tab-panel');

  if (mode === 'daily') {
    // Clear the screen of everything else — show ONLY the Daily Mobile-First view
    if (topHeader) topHeader.style.display = 'none';
    if (weekStrip) weekStrip.style.display = 'none';
    if (modeBar) modeBar.style.display = 'none';
    if (tabs) tabs.style.display = 'none';
    panels.forEach(p => { p.style.display = 'none'; });
    if (wView) wView.style.display = 'none';
    if (dView) dView.style.display = 'block';
    renderOnePagerViews();
  } else if (mode === 'weekly') {
    if (tabs) tabs.style.display = 'none';
    panels.forEach(p => { p.style.display = 'none'; });
    if (dView) dView.style.display = 'none';
    if (wView) wView.style.display = 'block';
    renderOnePagerViews();
  } else {
    // Desktop View: Weekly Check-In (Photos & Commentary) + Settings & Sync (Garmin + 2FA)
    if (topHeader) topHeader.style.display = '';
    if (weekStrip) weekStrip.style.display = 'grid';
    if (modeBar) modeBar.style.display = 'flex';
    if (dView) dView.style.display = 'none';
    if (wView) wView.style.display = 'none';
    if (tabs) tabs.style.display = 'grid';
    panels.forEach(p => { p.style.display = ''; });
  }
};

if (window.location.search.includes('mode=desktop') || window.location.search.includes('mode=full') || window.location.search.includes('mode=checkin')) {
  setTimeout(() => window.openDesktopTab('checkin'), 120);
} else if (window.location.search.includes('mode=settings')) {
  setTimeout(() => window.openDesktopTab('integrations'), 120);
} else if (window.location.search.includes('mode=weekly')) {
  setTimeout(() => window.setOnePagerMode('weekly'), 120);
} else {
  // Mobile-first default: open the clean, cleared-screen Daily Update view (with 1-click switch to Desktop Weekly Check-In & Settings)
  setTimeout(() => window.setOnePagerMode('daily'), 120);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initRealDataAndProgress, 100);
  });
} else {
  initRealDataAndProgress();
}

window.loadCohortBlocks = async function() {
  try {
    const res = await fetch('/api/challenge/blocks');
    const data = await res.json();
    if (!data.ok) return;
    const authBtn = document.getElementById('hdr-auth-btn');
    if (authBtn && data.active_profile) {
      authBtn.textContent = `👤 ${data.active_profile.client_name} · Sign In / Block`;
    }
    const box = document.getElementById('cohort-blocks-manager-box');
    if (!box) return;
    const blocks = data.blocks || [];
    const activeBlock = blocks.find(b => b.status === 'Active') || blocks[0];
    const upcomingBlock = blocks.find(b => b.status === 'Upcoming') || blocks[blocks.length - 1];
    box.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0.6rem;margin-bottom:0.85rem">
        ${blocks.map(b => `
          <div style="padding:0.65rem;border-radius:10px;background:var(--surface-2);border:1px solid ${b.status === 'Active' ? 'var(--green)' : 'var(--border)'}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:0.35rem;margin-bottom:0.3rem">
              <strong style="font-size:0.8rem;color:#fff">${b.name}</strong>
              <span class="badge ${b.status === 'Active' ? 'badge-green' : b.status === 'Upcoming' ? 'badge-blue' : 'badge-amber'}">${b.status}</span>
            </div>
            <div style="font-size:0.71rem;color:#cbd5e1;margin-bottom:0.25rem">
              🗓️ Pre-Coach: <strong>${b.pre_coaching_date}</strong> · Wk 1–8: <strong>${b.start_date} → ${b.end_date}</strong>
            </div>
            <div style="font-size:0.68rem;color:var(--muted);margin-bottom:0.4rem">
              ⏸️ Gap / Break: ${b.gap_weeks_after || 2} wk(s) · ${b.notes || ''}
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:0.35rem;flex-wrap:wrap">
              <span class="badge badge-green">🎟️ Code: ${b.invite_code} (${b.member_count || 0}/${b.max_members || 40})</span>
              <button class="btn btn-sm" onclick="copyBlockInvite('${b.invite_code}')">📋 Copy Invite URL</button>
            </div>
            ${(b.members && b.members.length) ? `
              <div style="margin-top:0.45rem;padding-top:0.4rem;border-top:1px solid var(--border);font-size:0.7rem;color:#cbd5e1">
                ${b.members.map(m => `
                  <span style="display:inline-flex;align-items:center;gap:0.25rem;background:#080b09;border:1px solid var(--border);border-radius:6px;padding:0.15rem 0.4rem;margin:0.1rem">
                    <strong>${m.client_name}</strong> ${m.is_returning_block ? '🔁14k' : '🆕10k'}
                    <button class="btn btn-sm" style="padding:0.05rem 0.3rem;font-size:0.62rem" onclick="quickSwitchChallenger(${m.profile_id})">View</button>
                  </span>
                `).join('')}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>

      <div class="grid-2" style="margin-bottom:0.5rem">
        <div style="padding:0.65rem;border-radius:10px;background:#080b09;border:1px solid var(--border)">
          <div style="font-size:0.78rem;font-weight:800;color:var(--green);margin-bottom:0.45rem">➕ Create New 8-Week Cohort Block</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin-bottom:0.45rem">
            <input type="text" id="new-block-name" placeholder="e.g. Block 4 · Autumn 2027" style="font-size:0.74rem" />
            <input type="date" id="new-block-start" value="2027-08-16" title="Week 1 Monday Start Date" style="font-size:0.74rem" />
            <input type="text" id="new-block-code" placeholder="Invite Code (e.g. CS-AUG2027)" style="font-size:0.74rem" />
            <select id="new-block-status" style="font-size:0.74rem">
              <option value="Upcoming">Upcoming</option>
              <option value="Active">Active</option>
            </select>
          </div>
          <button class="btn btn-green btn-sm" onclick="createNewCohortBlock()">🗓️ Create 8-Week Block</button>
        </div>

        <div style="padding:0.65rem;border-radius:10px;background:#080b09;border:1px solid var(--border)">
          <div style="font-size:0.78rem;font-weight:800;color:var(--blue);margin-bottom:0.45rem">🔁 Rollover Returning Members to Next Block</div>
          <p style="font-size:0.7rem;color:var(--muted);margin-bottom:0.45rem">
            Carries continuing members into the next 8-week cohort block and automatically upgrades their step target to <strong>14,000 steps/day</strong>.
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:0.35rem;align-items:center">
            <select id="roll-from-block" style="font-size:0.72rem">
              ${blocks.map(b => `<option value="${b.id}" ${activeBlock && b.id === activeBlock.id ? 'selected' : ''}>From: ${b.name}</option>`).join('')}
            </select>
            <select id="roll-to-block" style="font-size:0.72rem">
              ${blocks.map(b => `<option value="${b.id}" ${upcomingBlock && b.id === upcomingBlock.id ? 'selected' : ''}>To: ${b.name}</option>`).join('')}
            </select>
            <button class="btn btn-green btn-sm" onclick="rolloverBlockMembers()">🔁 Rollover</button>
          </div>
          <div style="margin-top:0.45rem;font-size:0.68rem;color:var(--muted)">
            💳 <strong>Signup / Payment Form Webhook:</strong> <code>POST /api/challenge/blocks/webhook/enroll</code> (auto-creates challenger + sets invite code).
          </div>
        </div>
      </div>
    `;
  } catch (e) {
    console.warn('loadCohortBlocks error:', e);
  }
};

window.copyBlockInvite = function(code) {
  const url = `${window.location.origin}/challenge/login?code=${encodeURIComponent(code)}`;
  if (navigator.clipboard) navigator.clipboard.writeText(url);
  showToast(`📋 Copied Invite Link: ${url}`);
};

window.createNewCohortBlock = async function() {
  const name = document.getElementById('new-block-name')?.value || 'New 8-Week Block';
  const start_date = document.getElementById('new-block-start')?.value || '2027-08-16';
  const invite_code = document.getElementById('new-block-code')?.value || '';
  const status = document.getElementById('new-block-status')?.value || 'Upcoming';
  const res = await fetch('/api/challenge/blocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, start_date, invite_code, status })
  });
  const data = await res.json();
  if (data.ok) {
    showToast(`✅ Created ${data.block.name} (${data.block.invite_code})`);
    loadCohortBlocks();
  }
};

window.rolloverBlockMembers = async function() {
  const from_block_id = Number(document.getElementById('roll-from-block')?.value || 0);
  const to_block_id = Number(document.getElementById('roll-to-block')?.value || 0);
  const res = await fetch('/api/challenge/blocks/rollover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_block_id, to_block_id })
  });
  const data = await res.json();
  if (data.ok) {
    showToast(`🔁 Rolled over ${data.rolled_over_count} member(s) into next block (14k steps/day)!`);
    loadCohortBlocks();
    if (typeof loadCohortBoard === 'function') loadCohortBoard();
  }
};

window.quickSwitchChallenger = async function(profileId) {
  const res = await fetch('/api/challenge/auth/switch-user', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId })
  });
  const data = await res.json();
  if (data.ok) {
    showToast(`👤 Switched active challenger to ${data.client_name}`);
    if (typeof loadOverview === 'function') await loadOverview(STATE.date);
    await refreshProgressSummary();
  }
};

window.exportChallengerBackupJson = async function() {
  const res = await fetch('/api/challenge/backup/export');
  const data = await res.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `cs-fitness-backup-${(data.client_name || 'user').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.json`;
  a.click();
  showToast('💾 Downloaded full challenger backup JSON!');
};

window.importChallengerBackupJson = async function(event) {
  const file = event.target?.files?.[0];
  if (!file) return;
  const text = await file.text();
  const payload = JSON.parse(text);
  const res = await fetch('/api/challenge/backup/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) {
    showToast(`✅ Restored ${data.restored.daily_checkins} check-ins & ${data.restored.daily_activities} activities!`);
    if (typeof loadOverview === 'function') await loadOverview(STATE.date);
    await refreshProgressSummary();
  }
};

window.syncMyAccountStatus = async function() {
  try {
    const res = await fetch('/api/challenge/auth/status');
    const data = await res.json();
    if (!data.ok) return;
    const authBtn = document.getElementById('hdr-auth-btn');
    if (authBtn && data.client_name) {
      authBtn.textContent = `👤 ${data.client_name}${data.username ? ' (@' + data.username + ')' : ''}`;
    }
    const emailInput = document.getElementById('my-acct-email');
    if (emailInput && data.email && document.activeElement !== emailInput) {
      emailInput.value = data.email;
    }
    const acctEmailEl = document.getElementById('acct-email-input');
    if (acctEmailEl && document.activeElement !== acctEmailEl) {
      acctEmailEl.value = data.email || '';
    }
    const acctUserEl = document.getElementById('acct-username-input');
    if (acctUserEl && document.activeElement !== acctUserEl) {
      acctUserEl.value = data.username || '';
    }
    const verBadge = document.getElementById('acct-email-verified-badge');
    const resendBtn = document.getElementById('btn-resend-verify-email');
    if (verBadge) {
      if (data.email_verified) {
        verBadge.textContent = '✅ Email Verified';
        verBadge.className = 'badge badge-green';
        if (resendBtn) resendBtn.style.display = 'none';
      } else if (data.email) {
        verBadge.textContent = '📧 Pending Email Verification';
        verBadge.className = 'badge badge-amber';
        if (resendBtn) resendBtn.style.display = 'inline-flex';
      } else {
        verBadge.textContent = 'Add Email to Verify';
        verBadge.className = 'badge badge-blue';
        if (resendBtn) resendBtn.style.display = 'none';
      }
    }
    const roleBadge = document.getElementById('my-acct-role-badge');
    const isAdmin = data.role === 'admin';
    if (roleBadge) {
      roleBadge.textContent = isAdmin ? '🛡️ Admin / Coach' : 'Challenger';
      roleBadge.className = isAdmin ? 'badge badge-green' : 'badge badge-blue';
    }
    const hdrAdminBtn = document.getElementById('hdr-admin-btn');
    if (hdrAdminBtn) hdrAdminBtn.style.display = isAdmin ? 'inline-flex' : 'none';
    const callout = document.getElementById('admin-portal-callout');
    if (callout) callout.style.display = isAdmin ? 'block' : 'none';
  } catch (e) {}
};

window.saveMyAccountDetails = async function() {
  const email = document.getElementById('acct-email-input')?.value?.trim() || '';
  const username = document.getElementById('acct-username-input')?.value?.trim() || '';
  const statusMsg = document.getElementById('acct-verify-status-msg');
  const res = await fetch('/api/challenge/auth/update-account', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username })
  });
  const data = await res.json();
  if (!data.ok) {
    showToast(`⚠️ ${data.error || 'Could not update account'}`);
    return;
  }
  showToast('✅ Updated Email & Username!');
  if (statusMsg && data.verification_url && !data.email_verified) {
    statusMsg.innerHTML = `📧 Verification link ready: <a href="${data.verification_url}" style="color:var(--green);font-weight:800">Click to verify ${data.email}</a>`;
  }
  await window.syncMyAccountStatus();
};

window.resendMyVerificationEmail = async function() {
  const email = document.getElementById('acct-email-input')?.value?.trim() || '';
  const statusMsg = document.getElementById('acct-verify-status-msg');
  const res = await fetch('/api/challenge/auth/resend-verification', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  const data = await res.json();
  if (!data.ok) {
    showToast(`⚠️ ${data.error || 'Could not send verification email'}`);
    return;
  }
  if (statusMsg && data.verification_url) {
    statusMsg.innerHTML = `${data.email_sent ? '📧 Sent to inbox! Or click: ' : '📧 Click to verify now: '}<a href="${data.verification_url}" style="color:var(--green);font-weight:800">✅ Verify ${data.email}</a>`;
  }
  showToast('📧 Verification link sent & ready!');
};

window.saveMyAccountSettings = async function() {
  const email = document.getElementById('my-acct-email')?.value?.trim() || '';
  const new_password = document.getElementById('my-acct-new-pw')?.value || '';
  if (!email && !new_password) {
    showToast('Enter an email address or new password to save');
    return;
  }
  if (new_password && new_password.length >= 4) {
    const res = await fetch('/api/challenge/auth/set-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, new_password })
    });
    const d = await res.json();
    if (!d.ok) {
      showToast(`⚠️ ${d.error || 'Could not update password'}`);
      return;
    }
    document.getElementById('my-acct-new-pw').value = '';
    showToast('✅ Saved email & password!');
  } else if (email) {
    const st = await (await fetch('/api/challenge/auth/status')).json();
    await fetch('/api/challenge/admin/update-admin-account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: st.profile_id, email, role: st.role || 'challenger' })
    });
    showToast('✅ Saved email address!');
  }
  await window.syncMyAccountStatus();
};

setTimeout(() => { window.syncMyAccountStatus(); }, 300);



