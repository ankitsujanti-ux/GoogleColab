# Share a public link (no local .exe)

GitHub stores the **code**. A **public URL** people can open in a browser needs a free cloud host.

## 1) Code is on GitHub

Folder: https://github.com/ankitsujanti-ux/GoogleColab/tree/main/Medication-Adherence-Dashboard

## 2) Deploy on Render (recommended, free)

### Option A — Blueprint (easiest)

1. Open https://dashboard.render.com and sign in with **GitHub**.
2. Click **New +** → **Blueprint**.
3. Select repo `ankitsujanti-ux/GoogleColab` (root `render.yaml` points at this folder).
4. Optionally set `OPENAI_API_KEY` (and Twilio/SendGrid/Pushover if needed). Leave blank for view-only demo.
5. Click **Apply**. Wait 2–5 minutes.

### Option B — Web Service manually

1. **New +** → **Web Service** → connect `ankitsujanti-ux/GoogleColab`.
2. Set **Root Directory** to: `Medication-Adherence-Dashboard`
3. Build: `pip install -r requirements.txt`
4. Start: `python main.py`
5. Create Web Service.

Your public link will look like:

`https://medication-adherence-dashboard.onrender.com`

Share that HTTPS link with anyone.

### Notes

- Free Render services **sleep after ~15 minutes** of no traffic; the first open after sleep can take 30–60 seconds.
- Do **not** commit a `.env` file (API keys). Set secrets only in the Render dashboard.
- Local `http://192.168.x.x:5000` only works on your Wi‑Fi. The Render URL works from anywhere.
