# Publish portal online (GitHub Pages)

**Your live URL (after setup):**  
[https://ankitsujanti-ux.github.io/GoogleColab/](https://ankitsujanti-ux.github.io/GoogleColab/)

**Repo:** [github.com/ankitsujanti-ux/GoogleColab](https://github.com/ankitsujanti-ux/GoogleColab)

---

## One-time setup (do once)

1. Sign in to GitHub as **ankitsujanti-ux**.

2. Open the repo → **Settings** → **Pages** (left sidebar).

3. Under **Build and deployment** → **Source**, choose **GitHub Actions** (not “Deploy from branch”).

4. Save. You only need this once.

---

## Publish / update notes

From PowerShell:

```powershell
cd c:\Users\Ankit.Sujantee\projects\llm_engineering\learning-portal
.\publish.ps1
```

- First time: Git may ask you to sign in to GitHub.
- Wait ~1 minute, then open the live URL above.
- Bookmark that URL — use it from any device.

---

## Who can see it?

| Repo visibility | Who can open the site |
|-----------------|------------------------|
| **Public** (default) | Anyone with the link |
| **Private** | Only you (GitHub account); needs paid plan for private Pages |

Your course notes have no API keys. Keep it public for easy access, or make the repo private if you prefer.

---

## After each new day (Day 5, etc.)

1. Add `content/week1/day5.json` + update `manifest.json` (as usual).
2. Run `.\publish.ps1` again.
3. Refresh the live site.

---

## Troubleshooting

- **404** — Pages not enabled, or Actions still running. Check **Actions** tab on GitHub.
- **Old content** — Hard refresh: `Ctrl+Shift+R`.
- **publish.ps1 fails on push** — Install [Git for Windows](https://git-scm.com/), sign in, or push manually: clone GoogleColab, copy all files from `learning-portal` into it, commit, push to `main`.
