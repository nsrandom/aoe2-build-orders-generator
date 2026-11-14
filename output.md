# AoE2:DE Build Order Output Formatting Specification (`output.md`)

This document defines the required output file structure, shared CSS architecture, Light/Dark theme behavior, interactive Resource Bank chart, collapsible sections, row/step compression rules, RTS Overlay JSON schema, and chat summary formatting for all build orders generated in this repository.

---

## 1. Directory Layout & Shared Assets

### 1.1 Shared Stylesheet (`styles/build_order.css`)
- All reusable styling across build order HTML guides resides in `/Users/asif/Projects/aoe/build-orders/gemini/styles/build_order.css`.
- Generated HTML files MUST link to this shared stylesheet via relative path (`<link rel="stylesheet" href="../../styles/build_order.css">`) rather than embedding duplicate `<style>` blocks or static inline styles.

### 1.2 Per-Build Directory (`builds/<build_slug>/`)
Every build order resides in its own dedicated directory `/Users/asif/Projects/aoe/build-orders/gemini/builds/<build_slug>/` containing:

1. **`sim_<build_slug>.py`** — Build-specific 1-second discrete-event simulation engine (importing shared constants and models from `/Users/asif/Projects/aoe/build-orders/gemini/scripts/aoe2_data.py`).
2. **`generate_<build_slug>.py`** — Build runner that executes all variants, records `army_counts` and `resource_timeline` points, verifies invariants, prints milestone telemetry, and invokes `export_build_order_html()` and `export_rts_overlay_json()` from `/Users/asif/Projects/aoe/build-orders/gemini/scripts/exporters.py`.
3. **`<build_slug>.html`** — Standalone HTML build order guide linking to `../../styles/build_order.css`.
4. **`<build_slug>_<variant>.json`** — RTS Overlay / AoE Overlay compatible JSON file for each variant.

---

## 2. Standalone HTML Build Order Guide (`<build_slug>.html`)

All HTML reports are generated via `export_build_order_html(docs, title, output_path)` in `/Users/asif/Projects/aoe/build-orders/gemini/scripts/exporters.py`.

### 2.1 Light & Dark Mode Support (Default: Light Mode)
- **Default Theme:** The page defaults to **Light Mode** (`<meta name="color-scheme" content="light">`).
- **FOUC Prevention & Persistence:** Immediately after `<meta name="color-scheme" content="light">` in `<head>`, a minimal synchronous inline `<script>` restores any user-selected preference from `localStorage.getItem("color-scheme") ?? "light"`, preventing flashes of un-themed content.
- **Top-Right Theme Toggle Button:** The `<header class="page-header">` places a `<button type="button" class="theme-toggle" id="theme-toggle-btn">` in the top-right corner with **Moon** (switch to Dark mode) and **Sun** (switch to Light mode) SVG icons (`aria-hidden="true"`).
- **CSS Color-Scheme Sync:** `:root` declares `color-scheme: light dark` and maps `<meta name="color-scheme">` back to the CSS `color-scheme` property via `:has(> head > meta[name="color-scheme"][content="light"])` and `:has(> head > meta[name="color-scheme"][content="dark"])`, using `light-dark()` tokens with custom-property fallbacks in `/Users/asif/Projects/aoe/build-orders/gemini/styles/build_order.css`.

### 2.2 Top-Level Variant Tabs
- Every requested or map-dependent variant (e.g., `24+2` vs. `26+2 + Monastery & 2 Monks` vs. `26+2 No Monastery`, or `3 Deer Pushed` vs. `8 Chickens Milled` vs. `6 Chickens Long-Distance`) MUST be displayed in its own interactive top-level tab inside the single `<build_slug>.html` file.

### 2.3 Collapsible Sections (`<details open class="phase-block">`)
Because build order guides can be long, **every section inside each variant tab MUST be collapsible**:
- Each section is rendered as a native `<details open class="phase-block">` disclosure element with `<summary class="phase-title">` as its first child:
  1. **Steady-State & Telemetry Section** (`Steady-State & Telemetry`)
  2. **Resources Bank Over Time Chart Section** (`Resources Bank Over Time`)
  3. **Each Age / Phase Timeline Table Section** (`Dark Age`, `Feudal Transition`, `Feudal Age`, `Castle Transition`, `Castle Age`, `Imperial Transition`, `Imperial Age`)
- **Accessibility & Styling Rules:**
  - Do **not** place heading elements (`<h3>`, `<h4>`) inside `<summary>` (so screen readers do not strip heading semantics).
  - Hide the default marker (`list-style: none`) and render an animated directional chevron right before the summary label via `.phase-title::before` and `.phase-block[open] > .phase-title::before`.
  - Provide an **Expand all sections / Collapse all sections** button (`.toggle-all-btn` with `aria-expanded="true"`) in each variant header that toggles all `<details class="phase-block">` elements in that tab and stays synchronized via a capturing `toggle` listener.

### 2.4 Interactive Resources Bank Over Time Chart
- Each variant tab includes a collapsible **Resources Bank Over Time** section containing a responsive inline `<svg class="resource-chart-svg">` chart:
  - **Series:** Plots `Food`, `Wood`, `Gold`, and `Stone` stockpiles from `00:00` through the end of the build using `doc.resource_timeline` (sampled every `10s` plus every build row event, or extracted automatically from `doc.rows`).
  - **Age Milestone Markers:** Vertical dashed lines mark key age-click and age-arrival timestamps (`Feudal Click`, `Feudal Age`, `Castle Click`, `Castle Age`, `Imp Click`, `Imp Age`).
  - **Interactive Controls:** Series checkboxes toggle `Food`, `Wood`, `Gold`, and `Stone` curves on/off, and hovering over the chart moves a vertical crosshair and displays the exact `MM:SS`, `Food / Wood / Gold / Stone` stockpile, and `Army` count by type.

### 2.5 Timeline Table Columns (`14` Columns) & Army Counts in Notes
Every phase table renders the following 14 columns:

| Column Group | Column Header | Format & Meaning |
| :--- | :--- | :--- |
| **1. Pop** | `Pop / Vils` | Villager count (or compressed range) and total population including Scout + military: e.g., `7v (8 pop)` or `4–6v (5–7 pop)`. |
| **2. Timestamp** | `Time` | Exact simulation timestamp `MM:SS` (or compressed span `00:25 – 01:15`). |
| **3. Action** | `Villager Assignment / Action` | Action taken at that step, including walk times, building/tech resource deductions (`-100W`, `-150F, -50G`), and build/research durations. |
| **4–9. Food Villagers Breakdown** | `Sheep` \| `Boar` \| `Deer/Chk` \| `Berries` \| `Farms` \| `Total F` | Exact active villager count on each food source at the end of the step, plus bold `Total F` (`Sheep + Boar + Deer/Chk + Berries + Farms`). |
| **10–12. Other Vils** | `Wood` \| `Gold` \| `Stone` | Active villager counts on Wood (including TC stragglers), Gold, and Stone. |
| **13. Resource Bank** | `Resource Bank` | Exact simulated stockpile (`Food F / Wood W / Gold G / Stone S`) **after** paying for any buildings, units, or techs triggered on that row. |
| **14. Notes, Buildings & Army** | `Notes, Buildings & Army` | Renders a pill badge (`<span class="army-badge">Army: ...</span>`) showing the **count of army by unit type** (e.g., `Army: 1 Scout`, `Army: 38 Genoese · 4 Light Cav · 2 Monks`, `Army: 3 MAA · 8 Archers`) alongside tactical notes, animal transitions, and building queues. |

---

## 3. Continuous Villager & Action Row Compression

To keep build order tables scannable in-game, **consecutive villagers or repeated actions that perform the same task within the same phase MUST be compressed into a single row**.

### 3.1 HTML Table Row Compression (`compress_build_rows` in `scripts/exporters.py`)
1. **Continuous Villager Assignments:**
   - When consecutive villagers `Vil #A` through `Vil #B` are assigned to the same task in the same phase without intervening building/tech rows, merge them into **1 row**:
     - **`Pop / Vils`:** `A–Bv (P1–P2 pop)` — e.g., `4–6v (5–7 pop)`, `8–9v (9–10 pop)`, `13–15v (14–16 pop)`, `21–23v (22–24 pop)`.
     - **`Time`:** `MM:SS – MM:SS` spanning from the first villager's spawn/assignment to the last villager's spawn/assignment — e.g., `00:25 – 01:15`.
     - **`Villager Assignment / Action`:** `Vils #A–#B (N vils) -> <shared assignment>`.
     - **Villager Breakdown, Resource Bank & Army Badge:** Display the **end-of-group state** (the villager counts, resource stockpile, and `army_counts` after `Vil #B` is assigned).
     - **`Notes, Buildings & Army`:** Concatenate unique non-empty notes from the merged rows preceded by the end-of-group `Army:` badge.
2. **Multi-TC Boom Villager Waves:**
   - In mid-to-late Castle Age when 2–3 Town Centers are producing villagers continuously into Farms, Wood, and Gold, group consecutive villager spawns between major building/tech milestones into compressed wave rows (e.g., `36–48v (67 pop) | Vils #36–#48 (13 vils across 2 TCs) -> Seed Farms up to 14, Gold to 12 & Wood`).
3. **Consecutive Farm Seeds & Military Queues:**
   - Consecutive identical Farm placements (`Seed Horse Collar Farms #3–#5 (3 Farms, -60W each, 5s walk + 15s build).`) and consecutive identical military unit queues (`Queue Light Cavalry #3–#4 (2 units) at Stable...`) without intervening rows are compressed into a single row.
4. **Preventing Artificial Row Splits:**
   - Do not insert standalone informational rows (such as mid-hunt Boar #2 lure reminders at `04:43` or redundant `"Queue Unit #1"` logs right after a `"Building completes! Start Unit production"` row) in the middle of a continuous villager run. Fold that timing note into the `Notes, Buildings & Army` column of the corresponding villager row so consecutive villagers compress cleanly into 1 row.

---

## 4. RTS Overlay JSON Format & Compression (`<build_slug>_<variant>.json`)

All JSON files are exported via `export_rts_overlay_json()` in `/Users/asif/Projects/aoe/build-orders/gemini/scripts/exporters.py`.

### 4.1 JSON Schema
```json
{
  "name": "Italians Arena FC (24+2): Castle Drop -> Genoese + Light Cav (30s Castle Pause)",
  "civilization": "Italians",
  "author": "AoE2:DE Quantitative Build Optimizer",
  "source": "1-Second Discrete-Event Simulation (rules.md compliant)",
  "description": "...",
  "build_order": [
    {
      "villager_count": 6,
      "age": 1,
      "resources": { "wood": 0, "food": 6, "gold": 0, "stone": 0 },
      "notes": [
        "00:00–01:15 — Vils #1–#6: Build 2 Houses (@other/house.png@), then 6 on Sheep under TC (@animal/sheep.png@)."
      ]
    }
  ]
}
```

### 4.2 JSON Step Compression & Invariants
1. **Compressed Continuous-Villager Steps:**
   - Consecutive villagers assigned to the same resource/task MUST be represented as **a single step** in `build_order`, where `villager_count` is the cumulative villager total at the end of that continuous group (e.g., `6`, `7`, `9`, `10`, `11`, `12`, `15`, `16`, `17`, `18`, `19`, `20`, `23`, `24`).
2. **Strict Villager Sum Invariant:**
   - Every step in `build_order` MUST strictly satisfy:
     $$\text{resources.wood} + \text{resources.food} + \text{resources.gold} + \text{resources.stone} = \text{villager\_count}$$
   - `export_rts_overlay_json()` raises a `ValueError` if any step violates this equality.
3. **Asset Icon Tags:**
   - Reference icons using `@category/icon.png@` tags defined in `RTS_ICONS` in `/Users/asif/Projects/aoe/build-orders/gemini/scripts/exporters.py`.

---

## 5. Chat Response Summary Rules

When presenting build order results to the user in chat:
1. **Milestone Comparison Table:** Include a concise Markdown table comparing all variants across major timings (`Feudal Click`, `Feudal Arrival`, `Castle Click`, `Castle Arrival & Bank`, `Defensive/Forward Castle Ready`, key military/tech milestones, `3 TCs Ready`, `Imperial Click`, `Imperial Arrival`, and `Total Animal Rot`).
2. **Tradeoff Analysis & Question Answers:** Directly answer any feasibility questions using exact resource bank and timing deltas from the 1-second simulation.
3. **Clickable File Links:** Always provide clickable `[basename](file:///absolute/path)` links to the generated `.html`, `.css`, `.json`, and `.py` files.
