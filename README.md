# LLM Engineering — Self Learning Portal

A local, book-style reference built from course notebooks and lecture transcripts.

## Run locally

Browsers block `fetch()` on `file://` URLs. From this folder:

```bash
python -m http.server 8080
```

On Windows, if `python` is not on PATH, use:

```bash
py -m http.server 8080
```

Or from the repo root (uses the project environment):

```bash
cd learning-portal
uv run python -m http.server 8080
```

Open [http://localhost:8080](http://localhost:8080).

## Live site (any device)

**URL:** [https://ankitsujanti-ux.github.io/GoogleColab/](https://ankitsujanti-ux.github.io/GoogleColab/)

Publish updates: run `.\publish.ps1` from this folder. See [DEPLOY.md](DEPLOY.md).

## Add a new day (e.g. Day 5)

1. Create `content/week1/day5.json` (copy structure from `day4.json`).
2. Add an entry to `content/manifest.json` under the week's `days` array:

```json
{
  "id": "day5",
  "title": "Day 5 — …",
  "file": "week1/day5.json",
  "sources": ["week1/day5.ipynb", "lecture transcript"]
}
```

3. Refresh the browser — the new chapter appears in the sidebar.

## Add a day (your workflow)

Send:

- Notebook path (e.g. `week1/day5.ipynb`)
- Lecture transcript (paste in chat)

Say: **"Add week1 day5 to the learning portal"**

The assistant will add `content/week1/day5.json` + one line in `manifest.json`. Refresh the browser.

## Chapter format (same as Day 4)

- **Read in order** — `step` 1, 2, 3… on each section
- **Technical terms kept** — plain English, no dumbing down labels
- **Yellow `remember` line** — one takeaway per step
- **`points`** — short bullets, sequential (each step builds on the last)
- **`visual`** — optional diagram (`three-cards`, `attention`, `tokens`, `compare`)
- **`cheatSheet`** — recap at bottom, same order as steps

Copy `content/week1/day4.json` as a template for new days.
