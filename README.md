# AoE2:DE Quantitative Build Order Simulator & Exporter

A per-second discrete-event simulator and exporter for *Age of Empires II: Definitive Edition* build orders.  
  
The computations and rules were verified against game data (as found online), including walking/gathering timings, animal rot, lumber camp decay, dynamic Market pricing, and late-command robustness checks. Post-simulation, the build orders are exported as interactive HTML guides and RTS Overlay compatible JSON.

## Included Build Orders

Open [`builds/index.html`](builds/index.html) in a browser to browse the included guides.

## Project Structure

- [`rules.md`](rules.md) — Authoritative gameplay, eco, walking, and robustness specifications.
- [`output.md`](output.md) — HTML report, interactive chart, row compression, and RTS Overlay JSON schema specs.
- [`prompt.md`](prompt.md) — Prompt template for generating new build orders.
- [`data/`](data/) — Game unit, building, technology, and civ bonus datasets.
- [`scripts/`](scripts/) — Shared simulation engine (`simulator.py`, `aoe2_data.py`, `backward_planner.py`, `exporters.py`, `test_rules_sync.py`).
- [`styles/`](styles/) — Shared Light/Dark stylesheet (`build_order.css`) and resource icons.
- [`builds/`](builds/) — Per-build simulators, generators, HTML guides, and RTS Overlay JSONs.

## Usage

Clone this repo, and give it to your favorite AI agent. I used Gemini to create these, so it's likely to work well.  
  
1. Use the prompt template in [`prompt.md`](prompt.md) to generate a new build order.  
2. Or just ask your agent to read the repository, especially the rules, and an existing build order's directory if you want to modify it.
3. Use a higher end model for better results, especially for new builds, since the agent will run the simulators and tweak the order accordingly, so it's a non-trivial exercise. I used Gemini Hydrogen (High) and Argon (High) to create this repo and its included build orders.
