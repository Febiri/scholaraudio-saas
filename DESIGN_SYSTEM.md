# ProfFeb Enterprise Design System & Architecture Guide

ProfFeb implements a unified design system modeled on tier-1 engineering and developer platforms (**Linear**, **Stripe**, **Vercel**, **Datadog**).

---

## 1. Design Tokens (`static/css/proffeb-design-system.css`)

All color, spacing, radius, typography, and motion tokens are defined as standard CSS variables on `:root` with automatic overrides for `html.dark` (`data-theme="dark"`).

### A. Surfaces & Color Palette

| Token | Light Theme | Dark Theme | Purpose |
| :--- | :--- | :--- | :--- |
| `--pf-bg-canvas` | `#f8fafc` | `#070a12` | Root page background |
| `--pf-bg-surface` | `#ffffff` | `#0d1322` | Cards, panels, sidebars |
| `--pf-bg-surface-elevated` | `#f1f5f9` | `#121a2d` | Hover states, table headers, drawers |
| `--pf-bg-surface-sunken` | `#edf2f7` | `#090e1a` | Code blocks, inset inputs |
| `--pf-text-primary` | `#0f172a` | `#f8fafc` | Headings, primary content (WCAG AAA) |
| `--pf-text-secondary` | `#475569` | `#94a3b8` | Subtitles, descriptions |
| `--pf-text-muted` | `#64748b` | `#64748b` | Labels, timestamps, subtle cues |
| `--pf-border-subtle` | `#e2e8f0` | `rgba(255,255,255,0.07)` | Dividers, card boundaries |
| `--pf-border-default` | `#cbd5e1` | `rgba(255,255,255,0.12)` | Input outlines, active borders |

### B. Engine Accent Colors

Each of ProfFeb's 7 academic engines has a dedicated accent variable:

* **Engine 01 (Research Studio)**: `--pf-engine-studio: #10b981;` (Emerald Teal)
* **Engine 02 (Conference Scout)**: `--pf-engine-scout: #6366f1;` (Indigo)
* **Engine 03 (Novelty Radar)**: `--pf-engine-radar: #8b5cf6;` (Violet)
* **Engine 04 (Reviewer Simulator)**: `--pf-engine-reviewer: #f43f5e;` (Rose/Coral)
* **Engine 05 (Funding Radar)**: `--pf-engine-grants: #0d9488;` (Teal)
* **Engine 06 (Lab Connector)**: `--pf-engine-lab: #0ea5e9;` (Sky Blue)
* **Engine 07 (Academic Co-Pilot)**: `--pf-engine-copilot: #06b6d4;` (Cyan)

### C. 4px/8px Spatial Scale & Typography

* **Spacing**: `--pf-space-1: 4px;` through `--pf-space-16: 64px;`
* **Typography**:
  * Sans-Serif (UI & Tables): `Inter`, system-ui
  * Monospace (Data, Code, Scores): `JetBrains Mono`
  * Academic Serif (Prose, Abstracts): `Newsreader` (optical size 16–72)
* **Motion**: 150ms–220ms `cubic-bezier(0.16, 1, 0.3, 1)` transitions. Reset under `@media (prefers-reduced-motion: reduce)`.

---

## 2. Reusable UI Components

* **Buttons**: `.pf-btn`, `.pf-btn-primary`, `.pf-btn-secondary`, `.pf-btn-ghost`, `.pf-btn-danger`, `.pf-btn-sm`, `.pf-btn-md`, `.pf-btn-lg`
* **Form Controls**: `.pf-input`, `.pf-select`, `.pf-textarea`
* **Cards & Panels**: `.pf-card`, `.pf-card-interactive`, `.pf-card-header`, `.pf-card-body`, `.pf-card-footer`
* **Badges**: `.pf-badge`, `.pf-badge-emerald`, `.pf-badge-indigo`, `.pf-badge-violet`, `.pf-badge-rose`, `.pf-badge-sky`, `.pf-badge-cyan`
* **Dense Data Tables**: `.pf-table-wrapper`, `.pf-table` (with sticky headers and hover rows)
* **States**:
  * Skeletons: `.pf-skeleton` (animated shimmer)
  * Empty States: `.pf-empty-state`, `.pf-empty-icon`, `.pf-empty-title`, `.pf-empty-desc`
* **Global Overlays**:
  * Toast Notifications: `ProfFebUI.toast({ title, message, type: 'success'|'error'|'warning'|'info' })`
  * Global Command Palette: `Cmd+K` / `Ctrl+K`

---

## 3. How to Add a New Engine Page

Adding a new engine (e.g. **Engine 08: Thesis Defense Simulator**) takes 4 simple steps:

### Step 1: Add Route in `backend/main.py`
```python
@app.get("/thesis-defense", response_class=HTMLResponse)
def serve_thesis_defense_page():
    return FileResponse(FRONTEND_DIR / "thesis_defense.html")
```

### Step 2: Define Engine Accent in `static/css/proffeb-design-system.css`
```css
:root {
  --pf-engine-thesis: #d97706; /* Amber */
  --pf-engine-thesis-bg: rgba(217, 119, 6, 0.1);
}
```

### Step 3: Register in Command Palette (`static/js/proffeb-ui.js`)
Add the new engine to `ProfFebUI.commandPalette.items`:
```javascript
{ title: 'Thesis Defense Simulator', category: 'Engines', url: '/thesis-defense', icon: '🎓', shortcut: '8' },
```

### Step 4: Create the Page (`frontend/thesis_defense.html`)
Use the standardized application shell:
```html
<!DOCTYPE html>
<html lang="en" class="dark" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <title>ProfFeb — Thesis Defense Simulator (Engine 08)</title>
  <link rel="stylesheet" href="/static/css/proffeb-design-system.css">
  <script src="/static/js/proffeb-ui.js" defer></script>
</head>
<body>
  <div class="pf-app-container">
    <!-- Persistent Collapsible Sidebar -->
    <aside id="pf-app-sidebar" class="pf-sidebar">
      <!-- Standard sidebar navigation -->
    </aside>

    <div class="pf-main-stage">
      <!-- Standard header with breadcrumbs -->
      <header class="pf-top-bar">
        <div class="pf-breadcrumbs">
          <a href="/">ProfFeb</a> / <span style="color: var(--pf-engine-thesis);">Thesis Defense</span>
        </div>
      </header>

      <!-- Engine specific workspace -->
      <main style="padding: 24px; max-width: 1400px; margin: 0 auto; width: 100%;">
        <!-- Engine Content -->
      </main>
    </div>
  </div>
</body>
</html>
```
