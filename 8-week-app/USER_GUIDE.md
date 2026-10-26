# CS Fitness 8-Week Challenge App — Quick Start Guide

**Live App URL:** `https://cs-fitness.onrender.com/challenge`  
**In-App Printable Guide:** `https://cs-fitness.onrender.com/challenge/guide`  
**Coach & Admin Portal (Chris, Laura, Ewan):** `https://cs-fitness.onrender.com/challenge/admin`

---

## PART 1: Challenger Guide (3 Simple Steps)

### 1. Set Up & Initial Work on Desktop App (Do Once at the Start)
1. **Sign In or Join Your 8-Week Block:**
   - Open **`https://cs-fitness.onrender.com/challenge/login`** on your laptop or desktop browser.
   - **New Challengers:** Click **🎟️ Join with Block Invite**, enter your Block Invite Code from Coach Chris (e.g., `CS-OCT2026`), your name, email, password, starting weight (`kg`), target weight, and body fat %. The app automatically calculates your personal **Calories, Protein, Carbs, Fats, Water (L), and Weekly Step Minimums**.
   - **Existing Challengers:** Sign in with your email address and password.
   - **Forgot Password?** Click **Forgot password?** on the sign-in screen (or the **🔑 Forgot / Set Password** tab) to reset your password using your Cohort Block Invite Code (`CS-OCT2026`) or a 6-digit Reset Code.
2. **Link Garmin Connect (Non-2FA & 2FA Supported) or Apple Health on Desktop:**
   - Click **⚙️ Settings** in the top bar to open **Settings & Sync**.
   - **Garmin Users WITHOUT 2FA:** Enter your **Garmin Connect Email & Password** and click **💾 Save & Connect** (leave the 6-digit 2FA box blank — you do **not** need to enable 2FA).
   - **Garmin Users WITH 2FA:** Click **💾 Save & Connect** first, then enter the 6-digit verification code sent by Garmin in the **🔐 Garmin 2-Factor Auth (2FA) Code** box and click **🔐 Verify 2FA Code & Connect**.
   - **Apple Watch / Apple Health Users:** In **Settings & Sync → 🍎 Apple Health + MyFitnessPal**, click **🧪 Test Apple Health (+ MFP) Sync Now** to test the workflow in 1 click, or click **📋 Copy My iOS Shortcut URL & JSON** to copy your personal tokenized webhook URL (`/api/challenge/sync/apple-health?token=...`) for an iPhone Shortcut.
   - Once connected on Desktop, your session is saved in the database — on your phone, you only ever need to tap **⌚ Sync with Garmin**!
3. **Day 1 Monday — Starting Weight & 3 Starting Photos:**
   - On the very first **Monday (Day 1)** of the block, open **📊 Weekly Check-In** on Desktop (selected on `Start Check-In · Day 1 Mon`), log your fasted starting weight, and upload your **3 Starting Photos** (`Side`, `Front`, `Back`).

---

### 2. Mobile Daily (Capturing Your Day-to-Day on Your Phone — Takes 30 Seconds)
1. **Open on Your Phone (Add to Home Screen):**
   - Open **`https://cs-fitness.onrender.com/challenge`** on your phone (in Safari tap **Share → Add to Home Screen**; in Chrome tap **Menu → Add to Home Screen**).
   - When you sign on, the screen is cleared of everything else and opens straight into your **Daily Update** screen (you can also use **📱 Daily Update** on the desktop web app).
2. **Tap `⌚ Sync with Garmin`:**
   - Tap the big blue **⌚ Sync with Garmin** button at the top to pull today's **Steps, Sleep, Weight, and Garmin Workouts** automatically.
3. **Update Your Daily Numbers (Large Text):**
   - Check or type your daily numbers in the large-text boxes:
     - **Weight (kg)** · **Steps**
     - **Calories (kcal)** · **Protein (g)** (from MyFitnessPal / Yazio)
     - **Water (L)** · **Sleep** (e.g., `8h 00m`)
4. **Select Training (`GYM`, `CARDIO`, `BOTH`, or `REST`) + Quick Note:**
   - No need to log every individual exercise at the gym — just tap **🏋️ GYM**, **🏃 CARDIO**, **🔥 BOTH**, or **🛋️ REST**.
   - In the **Workout / Training Note** box underneath, write a quick note if you trained (e.g., `3 x 5k at 5 min miles`).
5. **Tap Submit (`"Monday saved"` + Auto-Collated Weekly Round-Up):**
   - Tap the big green **✅ Submit Monday** button (dynamically matches the day of the week).
   - You'll get a confirmation message back saying **`✅ Monday saved`**, and your stats automatically collate into your **📊 Weekly Round-Up** card at the bottom of the screen!

---

### 3. Weekly Check-In on Desktop (Every Friday — Photos & Commentary)
1. **Open `📊 Weekly Check-In` on Desktop:**
   - Every **Friday**, open the app on your laptop/desktop and click **📊 Weekly Check-In**.
   - All of your daily entries from the week are already **auto-collated** into your Weekly Round-Up (Average Weight & % Loss, Average Steps, Average Calories, Average Protein, and your 7-day Mon–Sun table).
2. **Check-In & Photo Schedule:**
   - **Day 1 MONDAY (Start Check-In):** Upload your **3 Starting Photos** (`Side`, `Front`, `Back`) and starting weight.
   - **Week 1 FRIDAY Check-In (🚫 NO Photos Required):** Submit your Week 1 Friday weight and weekly commentary — **no photos are required on the first Friday** because you uploaded starting photos on Monday of the same week!
   - **Weeks 2–8 EVERY FRIDAY (+ 3 Photos):** Upload your **3 Friday Progress Photos** (`Side`, `Front`, `Back` — or click **✂️ Auto-Split 3-Pose Collage** to slice a single 3-pose image automatically).
3. **Add Your Weekly Commentary & Submit:**
   - Write how your week went in the **Your Weekly Write-Up / Reflection for Chris** box (wins, how training felt, schedule notes, or questions).
   - Click **✅ Submit Weekly Check-In to Coach (In-App)**.
4. **Coach Feedback:**
   - When Chris or Laura reviews your Friday check-in, their feedback and any updated Calorie/Protein targets appear right inside your **Weekly Check-In** view!

---

## PART 2: Coach & Admin Guide (For Chris, Laura & Ewan)

**Coach Portal URL:** `https://cs-fitness.onrender.com/challenge/admin`

1. **1. Cohort Summary (Built for ~100+ Challengers):**
   - Gives you a single-screen overview of the entire block for any check-in week (`Start · Day 1 Mon`, `Week 1 · Fri (No Photos)`, `Weeks 2–8 · Fri (+ 3 Photos)`).
   - Click any of the 5 top KPI cards (**Total Challengers**, **📬 Needs Coach Review**, **✅ Reviewed**, **📸 Has Weekly Photos**, **⚠️ Low Logging <3d**) to filter the table instantly, or search by name/email.
   - **Click any challenger's row** to open their full weekly review, 7-day sheet, and progress photos.
2. **2. Review & Feedback (In-App Coach Review):**
   - View the challenger's weekly averages, read their Friday write-up, inspect their 3 poses, type your coach feedback, optionally adjust their Daily Calories / Protein target, and click **💬 Publish Feedback to App**.
   - Use the **Next Challenger →** button in the top bar to step rapidly through all challengers during Friday check-in reviews.
3. **3. Weekly Sheet:**
   - Inspect all 7 days (`Mon–Sun`) of weight, weigh-in time, training type, steps, calories, macros, water, sleep, and logged workouts (with `×` to delete any errant workout).
4. **4. Compare Photos (Side-by-Side Studio):**
   - Compare **Start · Day 1 Mon (Start Photos)** against any **Friday Check-In (Weeks 2–8)** side-by-side across `Side`, `Front`, and `Back` poses with automatic scale weight change.
5. **5. Progress Trajectory:**
   - Full week-by-week table from Day 1 Monday Start through Week 8 Friday showing weight delta, step compliance, nutrition averages, and gym/cardio session counts.
6. **6. Manage Blocks & 7. Users & 3 Admins:**
   - Create sequential 8-week cohort blocks, onboard new challengers using Chris's exact formula engine, roll returning members into the next block (automatically sets their step minimum to `14,000` steps/day), and manage the 3 Admin logins (**Chris**, **Laura**, **Ewan**).
