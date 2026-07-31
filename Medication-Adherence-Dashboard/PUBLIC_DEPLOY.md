# Share a public link (no local .exe)

GitHub stores the **code**. A **public URL** people can open in a browser needs a free cloud host.

## 1) Code is on GitHub

Repo folder: https://github.com/ankitsujanti-ux/GoogleColab/tree/main/Medication-Adherence-Dashboard

## 2) Deploy on Render (recommended, free)

1. Open https://dashboard.render.com and sign in with GitHub.
2. Click **New +** → **Blueprint** (or **Web Service**).
3. Connect the repo `ankitsujanti-ux/Medication-Adherence-Dashboard`.
4. Render reads `render.yaml` automatically.
5. Set optional secrets (for AI / SMS / email features):
   - `OPENAI_API_KEY`
   - Twilio / SendGrid / Pushover keys if you use those features  
   Leave them blank for a view-only dashboard demo.
6. Click **Apply** / **Create Web Service**.
7. Wait 2–5 minutes. Your public link looks like:

   `https://medication-adherence-dashboard.onrender.com`

Share that HTTPS link with anyone.

### Notes

- Free Render services **sleep after ~15 minutes** of no traffic; the first open after sleep can take 30–60 seconds.
- Do **not** commit a `.env` file (API keys). Set secrets only in the Render dashboard.
- Local `http://192.168.x.x:5000` only works on your Wi‑Fi. The Render URL works from anywhere.
