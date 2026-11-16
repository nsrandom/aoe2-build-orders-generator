# AoE2:DE Build Order Generation Rules & Assumptions

This document is the authoritative specification for calculating, simulating, and exporting *Age of Empires II: Definitive Edition* build orders in this project.

---

## 1. Confirmed Rules

### 1.1 Movement & Walking Times
- **Initial Houses (`t = 0:00`):** The starting 3 villagers build 2 Houses immediately at `0:00` (`2` vils on House 1 $\rightarrow 18.75\text{s}$, `1` vil on House 2 $\rightarrow 25\text{s}$) and pay **only the 5-second return walk** to sheep under the Town Center (`5s` total walk).
- **Subsequent House Construction Walk Time:** **5 seconds each way** (`10s` round trip) every time a villager is sent from their current work to build a House and return to work.
- **Generic Building Construction Walk Time:** **10 seconds each way** (`20s` round trip) for any non-House building (e.g., Barracks, Archery Range, Stable, Blacksmith, Market, Castle, Monastery, University, Siege Workshop).
- **Sequential Building Construction:** **0 seconds walking time** between consecutive buildings if the same villager is tasked with constructing multiple buildings back-to-back (e.g., House $\rightarrow$ Barracks, or Blacksmith $\rightarrow$ Market).
- **Resource Camp Construction & Travel Time:**
  - Sending a villager to a Lumber Camp, Gold Mine, Stone Mine, or Berry Bushes takes **15 seconds one-way**.
  - When a villager walks `15s` to a resource to construct a drop-off camp (Lumber Camp, Mining Camp, Mill; `35s` build time) and remains there to gather, they pay **only the 15s one-way resource walk** plus the `35s` build time (`0s` walk after completion to start gathering).
- **Boar Luring & TC Garrison Shooting Idling:**
  - Luring villager pays **15 seconds walking time each way** (`30s` total luring interruption).
  - **TC Garrison Idling:** When each boar arrives under the TC, **6–8 villagers** under the TC garrison for **5 seconds** to shoot the boar down (`30–40` villager-seconds of lost gathering per boar).
  - **Post-Kill Transition:** After shooting the boar down, put **6+ villagers** onto the boar right away if only a small amount of food remains on the active sheep (finish any tiny leftover sheep right after or let 1 vil finish it, avoiding double rot).
- **Farms & TC Straggler Trees:**
  - **Farms:** **5 seconds** walking time to place a Farm (`60W`, `15s` build time), and **0 seconds** after completion to begin farming.
  - **TC Straggler Trees:** **3 seconds** walking time when switching a villager between under-TC food (sheep/boar/deer) and a TC straggler tree (`100W` per tree).
- **Long-Distance Gathering (Gold / Stone / Chickens):**
  - Allowed whenever it makes the build order more efficient (e.g., long-distance mining `50–70 Gold` for Loom or Dravidians MAA without spending `100W` on a Mining Camp, or long-distance hunting `6` chickens).
  - Each long-distance trip pays the **15 seconds each way** (`30s` round trip) travel time per carry capacity load (`10` for Gold/Stone, `35` for Hunter).

### 1.2 Resource Gathering, Variants & Decay
- **Map Variants (Deer vs. Chickens):**
  - Unless a prompt specifies one variant, **generate build order variants for both Deer and Chickens**.
  - **Deer Variant:** Assume **3 deer** (`140 Food` each = `420 Food` raw, `0.25 F/s` decay, `0.41 F/s` gather rate) are pushed by the Scout to the TC (`0s` walk time for hunters under the TC).
  - **Chicken Variant (`6–8` chickens at `75 Food` each, `0.125 F/s` decay):** Consider both **Milling** (often optimal for `8` chickens = `600 Food`) and **Long-Distancing** with `2` villagers (often optimal for `6` chickens = `450 Food`, saving `100W`).
- **Wood Cutting Efficiency Decay & Camp Refresh:**
  - Lumberjack gathering efficiency starts at **100%** (`0.39 wood/s` base).
  - Efficiency **drops by 1% every 20 seconds** (`3%` per minute) elapsed since the current Lumber Camp was completed.
  - Efficiency **resets to 100%** whenever a **new Lumber Camp** is completed.
  - **Refresh Target:** Aim to construct a new Lumber Camp when wood cutting efficiency drops to **60%–65%** (`700–800 seconds` / `11m 40s–13m 20s` after the previous Lumber Camp finished, typically around `14:00–15:40` in-game).
  - **Wood Priority Rule:** Never delay essential progression buildings (Military Buildings, Blacksmith, Market, Eco Upgrades, Houses, or required Farms) to refresh a Lumber Camp; when wood is constrained in early-to-mid Feudal Age, defer the Lumber Camp refresh until core buildings and farms are placed.
  - **Villager Density per Camp:** Aim for `7–8` villagers max per Lumber Camp; when expanding to `9+` lumberjacks, add a 2nd Lumber Camp (subject to the Wood Priority Rule) to prevent bumping and reset efficiency.
- **Animal Rot (Decay) & Villager Allocation Limits:**
  - Villagers must minimize rot by only slaughtering one animal of a given type at a time unless there are too many villagers to fit on a single carcass.
  - **Ideal villager counts per carcass/patch:**
    - **Sheep (Herdables):** `6` villagers (max `7` — never put more than `7` on sheep)
    - **Boar (Large Hunt):** `7–8` villagers (generally `9` or less; up to `10` allowed during age-up transition phases)
    - **Deer (Small Hunt):** `4` villagers (max `7` — never put more than `7` on deer)
    - **Chicken:** `2` villagers (`3–4` on a milled patch of `7` chickens)
  - Never slaughter a new sheep while a boar carcass is already open under the TC (shepherds finishing their current sheep must immediately switch onto the active boar, and if only a small amount of food remains on the sheep when the boar is shot down, put `6+` vils on the boar).
  - A small amount of additional rot is acceptable if it leads to macro efficiencies elsewhere.
- **Carried Resources on Re-tasking:**
  - Villagers do not lose carried resources when re-tasked at the TC or upon completing a drop-off camp.

### 1.3 Town Center, Age-Up & Default Technologies
- **End-of-Age TC Idle Allowance:** Build orders may wait up to **5 seconds of idle Town Center time** at the end of an age before clicking up.
- **Continuous TC Production:** Outside of the $\le 5\text{s}$ pre-click window, the Town Center must maintain continuous villager production (`25s` per villager, `50 Food`) or research (`Loom`, Age-Up) without unplanned idle time.
- **Loom Default:** Research **Loom** (`50G, 25s`) right before clicking Feudal Age by default, except in safe Fast Castle builds where it may be delayed if needed.
- **Economy Upgrade Defaults:**
  - Automatically include **Double-Bit Axe** (`100F, 50W, 25s`) upon reaching Feudal Age and **Bow Saw** (`150F, 100W, 50s`) upon reaching Castle Age.
  - Automatically include **Horse Collar** (`75F, 75W, 20s`) before seeding heavy farms (unless executing a tight all-in build).

### 1.4 Market Usage & Expected Prices
- **Occasional Market Usage:** Feel free to occasionally use the Market to balance resource stockpiles (e.g., hitting Age-up clicks, Castle/TC drops, or key upgrades without idling production).
- **Assumed Market Sell Prices (Gold received per `100` Food or Wood sold):**
  - **Feudal Age:** High prices (`~70 Gold` per `100` Food/Wood sold; `~70–91 Gold` per `100` Stone sold).
  - **Early to Mid Castle Age:** `~50 Gold` per `100` Food/Wood sold.
  - **Late Castle Age:** `~30 Gold` per `100` Food/Wood sold.
  - **Imperial Age:** `~15 Gold` per `100` Food/Wood sold.

### 1.5 Build Order Simplicity & Execution Buffer Policy
- **Tight Early Precision (`~20–30` Vils) vs. High-Level Later Macro:**
  - Humans can only follow a tight villager-by-villager build order for the first `~20–30` villagers (Dark Age + Feudal Transition for non-Fast-Castle builds; Dark Age + Feudal Age + Castle Click for Fast Castle builds).
  - **Combined Same-Resource Steps:** Whenever multiple consecutive villagers go to the same resource—including when the 1st villager builds a camp (`Lumber Camp`, `Mill`, `Mining Camp`) or `House` before gathering that resource—combine them into a single step (e.g., `3 vils to Wood after 1st vil builds Lumber Camp`).
  - **High-Level Macro Phases (Feudal+ for non-FC; Castle+ for FC):** Combine repetitive villager spawns, farm placements, houses, and continuous unit queues into high-level priority-loop instructions (e.g., `"Make vils continuously -> new vils go to stragglers & seed Farms every 60W, while producing X with leftover resources until <criteria>"`).
- **Imperfect Execution Buffer (Later Stages):**
  - Simulations apply a realistic human execution buffer in later ages (`~92%` effective macro gather efficiency in Feudal Age and `~90%` in Castle Age+, plus safety reserves before major clicks/buildings) to absorb villager transition friction, bumping, farm placement delays, and army micro overhead.
- **Resource Float Cap & Late-Game Scaling Rule:**
  - Unless intentionally banking resources for a concrete target (e.g., Age-Up click, Castle drop, or an expensive power-spike tech), avoid floating more than **`~500–1,000`** of any resource as the economy grows.
  - Dynamically spend surplus resources according to the build's current phase goals: add extra military production buildings (`Archery Ranges`, `Barracks`, `Stables`, `Siege Workshops`), queue eco/military upgrades, expand Town Centers, or rebalance surplus villagers (and Market trades per Section 1.4 if heavily skewed).
  - When a Castle Age build prioritizes ramping military quickly before Imperial Age (e.g., hitting an army threshold such as `50+` military units), scale extra military buildings aggressively early, then shift priority to **Imperial Age (`1000F, 800G`, `190s`)** — pausing/idling extra military buildings temporarily if needed so Imperial Age is reliably reached **before `40:00`**.
- **Ballistics Priority Rule (`20+` Ranged Units):**
  - Across all builds, once you have **`20+` ranged units** (Archers/Crossbowmen, Skirmishers, Cav Archers, Elephant Archers, Genoese, etc.), prioritize building a **University (`200W`)** and researching **Ballistics (`300W, 175G`)** ahead of extra production buildings, late TCs, or secondary upgrades — unless there is another explicit high-priority goal active (e.g., immediate Castle Age multi-TC boom drops or an imminent Age-Up click).

### 1.6 Required Output Formats & Directory Layout (`output.md`)
See `/Users/asif/Projects/aoe/build-orders/gemini/output.md` for the complete output formatting specification. In summary, for every requested build order, create a dedicated directory `builds/<build_slug>/` containing:
1. **Build-Specific Python Scripts (`sim_<build_slug>.py`, `generate_<build_slug>.py`):**
   - Placed directly inside `builds/<build_slug>/` next to the output files.
2. **Detailed HTML Build Order Report (`<build_slug>.html`):**
   - **Top-Level Tab Views:** Present all requested or map-dependent variants as top-level tabs.
   - **Sectioned Timeline Tables:** Broken into separate sections by phase (`Dark Age`, `Feudal Transition`, `Feudal Age`, `Castle Transition`, `Castle Age`, `Imperial Transition`, `Imperial Age`).
   - **Same-Resource & High-Level Macro Compression:** Consecutive villagers going to the same resource (including building the camp/house first) are combined into 1 row, and Feudal+ (non-FC) / Castle+ (FC) phases use high-level macro priority blocks.
   - **Strategy Comparison Section:** Interactive population line chart comparing all strategies (solid lines for Villager population, dashed lines of the same color for Military population), with checkboxes to show/hide each strategy as well as Villager and Military series.
3. **RTS Overlay Compatible JSON (`.json`):**
   - Follows the `RTS_Overlay` / `AoE Overlay` schema (`name`, `civilization`, `author`, `source`, `description`, `build_order` array of `{villager_count, age, resources: {wood, food, gold, stone}, notes}` using `@category/icon@` asset tags).
   - Same-resource villager steps (including camp/house builders) are combined into a single step, and later stages use concise macro priority steps.
   - Every step must satisfy `sum(resources.values()) == villager_count`.

---

## 2. Base Game Data & Constants (from `aoe2-de-tools` & AoE2:DE)

### 2.1 Base Villager Gather Rates (`res/sec` & `res/min`)
| Resource / Role | Base Gather Rate (`res/s`) | Base Gather Rate (`res/min`) | Carry Capacity | Notes / Tech Multipliers |
| :--- | :---: | :---: | :---: | :--- |
| **Hunter** (Boar / Deer) | `0.4100` | `24.60` | `35` | Mongols `+40%`, Goths `+15 carry` |
| **Shepherd** (Sheep / Turkey) | `0.3300` | `19.80` | `10` | Britons `+25%`, Tatars `+50% food` |
| **Forager** (Berries) | `0.3100` | `18.60` | `10` | Franks `+15%`, Portug. `+wood` |
| **Farmer** (Base) | `0.3383` | `20.30` | `10` | Includes standard farm walk |
| **Farmer** (Heavy Plow) | `0.3533` | `21.20` | `11` | |
| **Farmer** (Wheelbarrow) | `0.3838` | `23.03` | `13` | Near cap before Hand Cart |
| **Farmer** (Hand Cart) | `0.4000` | `24.00` | `15` | |
| **Lumberjack** (Base) | `0.3900` | `23.40` | `10` | `-1%` every `20s` (`-3%/min`); refresh LC at `60%–65%` |
| **Lumberjack** (Double-Bit Axe) | `0.4680` (`~0.47`) | `28.08` | `10` | `+20%` (`100F, 50W, 25s`) |
| **Lumberjack** (Bow Saw) | `0.5616` (`~0.56`) | `33.70` | `10` | `+20%` (`150F, 100W, 50s`) |
| **Gold Miner** (Base) | `0.3800` | `22.80` | `10` | |
| **Gold Miner** (Gold Mining) | `0.4370` (`~0.44`) | `26.22` | `10` | `+15%` (`100F, 75W, 30s`) |
| **Stone Miner** (Base) | `0.3600` | `21.60` | `10` | |
| **Stone Miner** (Stone Mining) | `0.4140` (`~0.41`) | `24.84` | `10` | `+15%` (`100F, 75W, 30s`) |

### 2.2 Natural Food Sources & Animal Rot Rates (Standard Arabia)
With $N$ villagers gathering at rate $r$ and carcass decay rate $d$, harvest duration is $T = \frac{F_0}{N \cdot r + d}$ and net food collected is $F_{\text{net}} = F_0 \cdot \frac{N \cdot r}{N \cdot r + d}$.

| Source | Count on Arabia | Initial Food ($F_0$) | Decay Rate ($d$) | Gather Rate ($r$) | Ideal Vils ($N$) | Net Yield at Ideal $N$ | Duration at Ideal $N$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sheep** | `8` | `100 F` | `0.25 F/s` | `0.33 F/s` | `6` (max `7`) | `88.8 F` (`11.2 F` rot) | `44.8 s` |
| **Boar** | `2` | `340 F` | `0.40 F/s` | `0.41 F/s` | `7–8` (max `9`; `10` trans.) | `303.2 F` (`36.8 F` rot @8) | `92.4 s` |
| **Deer** | `3` | `140 F` | `0.25 F/s` | `0.41 F/s` | `4` (max `7`) | `121.5 F` (`18.5 F` rot) | `74.1 s` |
| **Chicken** | `6–8` | `75 F` | `0.125 F/s` | `0.33 F/s` | `2` (max `4`) | `63.1 F` (`11.9 F` rot) | `95.5 s` |
| **Berry Bush** | `6` | `125 F` (`750 F` tot) | `0.00 F/s` | `0.31 F/s` | `4` | `125.0 F` (`0 F` rot) | `~100.8 s/bush` |
| **Farm (Base)** | — | `175 F` | `0.00 F/s` | `0.3383 F/s` | `1` | `175.0 F` | `517.3 s` |

### 2.3 Multi-Villager Construction Speed
When $n$ villagers construct a building with single-villager build time $t$:
$$T(n) = \frac{3 \cdot t}{n + 2}$$
