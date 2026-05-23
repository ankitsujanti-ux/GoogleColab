/**
 * LLM Engineering Learning Portal
 * Loads manifest.json + per-day JSON chapters. Add new days in manifest only.
 */

const MANIFEST_URL = "content/manifest.json";
const CONTENT_BASE = "content/";

const els = {
  portalTitle: document.getElementById("portal-title"),
  portalSubtitle: document.getElementById("portal-subtitle"),
  toc: document.getElementById("toc"),
  cover: document.getElementById("cover"),
  chapter: document.getElementById("chapter"),
  coverTitle: document.getElementById("cover-title"),
  coverDesc: document.getElementById("cover-desc"),
  btnTheme: document.getElementById("btn-toggle-theme"),
};

let manifest = null;
let activeChapterId = null;

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatInline(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderVisual(v) {
  if (!v?.type) return "";

  switch (v.type) {
    case "three-cards":
      return `
        <div class="visual visual-cards" role="img" aria-label="GPT means three things">
          ${v.cards
            .map(
              (c) => `
            <div class="card">
              <span class="card-letter">${escapeHtml(c.label)}</span>
              <strong>${escapeHtml(c.title)}</strong>
              <p>${escapeHtml(c.text)}</p>
            </div>`
            )
            .join("")}
        </div>`;

    case "attention":
      return `
        <div class="visual visual-attention" role="img" aria-label="Transformer looks at important words">
          <p class="visual-caption">Reading the word <strong>${escapeHtml(v.focus)}</strong> — also uses:</p>
          <div class="sentence">${escapeHtml(v.sentence)}</div>
          <div class="looks-at">
            ${(v.looksAt || [])
              .map((w) => `<span class="chip">${escapeHtml(w)}</span>`)
              .join("")}
          </div>
        </div>`;

    case "tokens":
      return `
        <div class="visual visual-tokens" role="img" aria-label="Text split into tokens">
          <p class="visual-caption">Your text → pieces the model sees</p>
          <div class="token-row">
            ${(v.pieces || [])
              .map((p) => `<span class="token">${escapeHtml(p)}</span>`)
              .join('<span class="token-arrow">→</span>')}
          </div>
          <p class="visual-hint">Example: ${escapeHtml(v.text || "")}</p>
        </div>`;

    case "flow":
      return `
        <div class="visual visual-flow" role="img" aria-label="Model progression">
          <div class="flow-row">
            ${(v.steps || [])
              .map((s) => {
                if (s.title === "→") {
                  return `<span class="flow-arrow">→</span>`;
                }
                return `
              <div class="flow-step">
                <strong>${escapeHtml(s.title)}</strong>
                ${s.text ? `<span>${escapeHtml(s.text)}</span>` : ""}
              </div>`;
              })
              .join("")}
          </div>
        </div>`;

    case "compare":
      return `
        <div class="visual visual-compare" role="img" aria-label="${escapeHtml(v.title || "Comparison")}">
          ${v.title ? `<p class="visual-caption">${escapeHtml(v.title)}</p>` : ""}
          <div class="compare-grid">
            ${["left", "right"]
              .map((side) => {
                const box = v[side];
                if (!box) return "";
                return `
              <div class="compare-box ${box.bad ? "compare-bad" : "compare-good"}">
                <h4>${escapeHtml(box.label)}</h4>
                <ol>${(box.lines || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>
              </div>`;
              })
              .join("")}
          </div>
        </div>`;

    default:
      return "";
  }
}

function renderToc(data) {
  els.portalTitle.textContent = data.title;
  els.portalSubtitle.textContent = data.subtitle || "";
  els.coverTitle.textContent = data.title;
  els.toc.innerHTML = "";

  data.weeks.forEach((week) => {
    const weekBlock = document.createElement("div");
    weekBlock.className = "toc-week";

    const weekTitle = document.createElement("p");
    weekTitle.className = "toc-week-title";
    weekTitle.textContent = week.title;
    weekBlock.appendChild(weekTitle);

    week.days.forEach((day) => {
      const chapterId = `${week.id}/${day.id}`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "toc-link";
      btn.dataset.chapterId = chapterId;
      btn.dataset.file = day.file;
      btn.textContent = day.title;
      btn.addEventListener("click", () => openChapter(chapterId, day));
      weekBlock.appendChild(btn);
    });

    els.toc.appendChild(weekBlock);
  });
}

function renderChapter(data, dayMeta) {
  const weekLabel = dayMeta?.weekTitle || "";
  const parts = [];

  parts.push(`
    <header class="chapter-header">
      <p class="chapter-meta">${escapeHtml(weekLabel)}</p>
      <h2 class="chapter-title">${escapeHtml(data.title)}</h2>
      <p class="chapter-summary">${formatInline(data.summary)}</p>
    </header>
  `);

  (data.sections || []).forEach((section) => {
    const stepLabel = section.step
      ? `<span class="step-badge">Step ${section.step}</span>`
      : "";
    let block = `
      <section class="section">
        <h3>${stepLabel}${escapeHtml(section.heading)}</h3>
    `;
    if (section.remember) {
      block += `<p class="remember">${formatInline(section.remember)}</p>`;
    } else if (section.analogy) {
      block += `<p class="analogy">${formatInline(section.analogy)}</p>`;
    }
    if (section.visual) {
      block += renderVisual(section.visual);
    }
    if (section.points?.length) {
      block += "<ul>";
      section.points.forEach((p) => {
        block += `<li>${formatInline(p)}</li>`;
      });
      block += "</ul>";
    }
    if (section.code) {
      block += `<pre class="code-block"><code>${escapeHtml(section.code)}</code></pre>`;
    }
    block += "</section>";
    parts.push(block);
  });

  if (data.cheatSheet?.length) {
    let c = '<div class="cheat-sheet"><h3>Quick recap (same order)</h3><ul>';
    data.cheatSheet.forEach((line) => {
      c += `<li>${formatInline(line)}</li>`;
    });
    c += "</ul></div>";
    parts.push(c);
  } else if (data.glossary?.length) {
    let g = '<div class="glossary"><h3>Words to know</h3><dl>';
    data.glossary.forEach(({ term, definition }) => {
      g += `<dt>${escapeHtml(term)}</dt><dd>${escapeHtml(definition)}</dd>`;
    });
    g += "</dl></div>";
    parts.push(g);
  }

  if (data.practice?.length) {
    let p = '<div class="practice"><h3>Practice</h3><ol>';
    data.practice.forEach((item) => {
      p += `<li>${escapeHtml(item)}</li>`;
    });
    p += "</ol></div>";
    parts.push(p);
  }

  if (dayMeta?.sources?.length) {
    parts.push(
      `<p class="sources">Sources: ${dayMeta.sources.map(escapeHtml).join(" · ")}</p>`
    );
  }

  els.chapter.innerHTML = parts.join("");
}

async function openChapter(chapterId, day, weekTitle) {
  const file = day.file;
  const url = CONTENT_BASE + file;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${url}`);
    const data = await res.json();

    activeChapterId = chapterId;
    renderChapter(data, { weekTitle, sources: day.sources });

    els.cover.classList.add("hidden");
    els.chapter.classList.remove("hidden");

    document.querySelectorAll(".toc-link").forEach((link) => {
      link.classList.toggle("active", link.dataset.chapterId === chapterId);
    });

    history.replaceState({ chapterId }, "", `#${chapterId}`);
    window.scrollTo(0, 0);
    els.chapter.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    console.error(err);
    els.chapter.innerHTML = `<p>Could not load chapter: ${escapeHtml(err.message)}. Run a local server from learning-portal (see cover page).</p>`;
    els.cover.classList.add("hidden");
    els.chapter.classList.remove("hidden");
  }
}

function findChapter(chapterId) {
  if (!manifest) return null;
  for (const week of manifest.weeks) {
    for (const day of week.days) {
      const id = `${week.id}/${day.id}`;
      if (id === chapterId) {
        return { day, weekTitle: week.title };
      }
    }
  }
  return null;
}

function initTheme() {
  const stored = localStorage.getItem("portal-theme");
  if (stored === "dark") document.documentElement.setAttribute("data-theme", "dark");
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  if (isDark) {
    document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("portal-theme", "light");
  } else {
    document.documentElement.setAttribute("data-theme", "dark");
    localStorage.setItem("portal-theme", "dark");
  }
}

async function init() {
  initTheme();
  els.btnTheme.addEventListener("click", toggleTheme);

  try {
    const res = await fetch(MANIFEST_URL);
    if (!res.ok) throw new Error("manifest not found");
    manifest = await res.json();
    renderToc(manifest);

    const hash = location.hash.slice(1);
    if (hash) {
      const found = findChapter(hash);
      if (found) await openChapter(hash, found.day, found.weekTitle);
    }
  } catch (err) {
    els.toc.innerHTML = `<p style="padding:1rem;color:#a00;">${escapeHtml(err.message)} — start server in learning-portal folder.</p>`;
  }

  window.addEventListener("popstate", (e) => {
    const id = e.state?.chapterId || location.hash.slice(1);
    if (!id) {
      els.cover.classList.remove("hidden");
      els.chapter.classList.add("hidden");
      document.querySelectorAll(".toc-link").forEach((l) => l.classList.remove("active"));
      return;
    }
    const found = findChapter(id);
    if (found) openChapter(id, found.day, found.weekTitle);
  });
}

init();
