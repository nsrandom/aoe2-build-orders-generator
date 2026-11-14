# Prompt Template for Generating New AoE2:DE Build Orders

```markdown
Generate an Age of Empires II: Definitive Edition (AoE2:DE) build order for the following goal:

**Goal:** [INSERT BUILD ORDER GOAL HERE — e.g., "Fast Castle with Italians such that we have enough stone to do a Castle drop on reaching Castle Age, followed by continuous 1 TC villager + Genoese Crossbowman production"]

### Instructions
1. **Read Rules:** Read `/Users/asif/Projects/aoe/build-orders/gemini/rules.md` and follow all rules, assumptions, output formats, and directory layout requirements defined there.
2. **Use Shared Engine (`scripts/`):**
   - `/Users/asif/Projects/aoe/build-orders/gemini/scripts/aoe2_data.py` (`AoE2Database`, `ResourceBundle`, `RuleConfig`, `ANIMALS`, `CIV_BUILD_BONUSES`)
   - `/Users/asif/Projects/aoe/build-orders/gemini/scripts/backward_planner.py` (`BackwardPlanner`, `ContinuousProductionItem`)
   - `/Users/asif/Projects/aoe/build-orders/gemini/scripts/exporters.py` (`BuildOrderDocument`, `DetailedBuildRow`, `RTSOverlayStep`, `RTS_ICONS`, `export_build_order_html`, `export_rts_overlay_json`)
3. **Reference Implementation:**
   - Check `/Users/asif/Projects/aoe/build-orders/gemini/builds/dravidian_maa_into_archers/sim_dravidians_maa.py` and `generate_dravidians_maa.py` for how the 1-second discrete-event simulation and exporters are wired together.
4. **Output:**
   - Save the build-specific Python scripts, standalone HTML guide, and RTS Overlay JSON files in `/Users/asif/Projects/aoe/build-orders/gemini/builds/<build_slug>/`.
```

---

## Recommended Model & Thinking Level

- **Best Everyday Choice (Fast + Daily Quota): `Gemini 4 Hydrogen (High)` or `Gemini 4 Hydrogen (Extra High)`**
  - Because the core simulation engine (`scripts/`) and reference build (`builds/dravidian_maa_into_archers/`) are already in place, the agent doesn't need to guess the math in its head—it writes the build script, runs the 1-second Python simulator, and tunes any resource bottlenecks from actual telemetry.
  - **Hydrogen (High)** is ideal for standard openings (Scouts, Archers, Fast Castle); step up to **Hydrogen (Extra High)** for tight multi-resource builds (e.g. Italians Fast Castle into Castle Drop + Genoese Crossbows).
- **Best for Complex New Civ Mechanics: `Gemini 4 Argon (High)` (or `Argon (Medium)` to save weekly quota)**
  - Use **Argon (High)** when a build order introduces brand-new mechanics that require extending the engine (e.g. Market buy/sell optimization, Khmer building-skipping, Poles Folwark instant food collection, or multi-TC boom math).
