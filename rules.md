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
- **Boar Luring:** **15 seconds walking time each way** (`30s` total luring interruption for the luring villager).
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
  - Efficiency **drops by 1% every 15 seconds** (`4%` per minute) elapsed since the current Lumber Camp was completed.
  - Efficiency **resets to 100%** whenever a **new Lumber Camp** is completed.
  - **Refresh Target:** Aim to construct a new Lumber Camp when wood cutting efficiency drops to **60%** (`600 seconds` / `10 minutes` after the previous Lumber Camp finished).
- **Animal Rot (Decay) & Villager Allocation Limits:**
  - Villagers must minimize rot by only slaughtering one animal of a given type at a time unless there are too many villagers to fit on a single carcass.
  - **Ideal villager counts per carcass/patch:**
    - **Sheep (Herdables):** `6` villagers (up to `8` max for short periods)
    - **Boar (Large Hunt):** `7` villagers (up to `9` max for short periods)
    - **Deer (Small Hunt):** `4` villagers (up to `6` max for short periods)
    - **Chicken:** `2` villagers (up to `4` max for short periods)
  - Up to **+2 extra villagers** beyond the ideal number are permitted for short periods to avoid slaughtering a second animal early and incurring double rot.
  - Never slaughter a new sheep while a boar carcass is already open under the TC (shepherds finishing their current sheep must immediately switch onto the active boar).
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

### 1.4 Required Output Formats & Directory Layout
For every requested build order, create a dedicated directory `builds/<build_slug>/` containing:
1. **Build-Specific Python Scripts (`sim_<build_slug>.py`, `generate_<build_slug>.py`):**
   - Placed directly inside `builds/<build_slug>/` next to the output files.
2. **Detailed HTML Build Order Report (`<build_slug>.html`):**
   - **Top-Level Tab Views:** Present the map variants (e.g., `3 Deer Pushed`, `8 Chickens Milled`, `6 Chickens Long-Distance`) as top-level tabs.
   - **Sectioned Villager-by-Villager Timeline Tables:** Broken into separate sections by phase (`Dark Age`, `Feudal Transition`, `Feudal Age`, `Castle Transition`, `Castle Age`, etc.) with columns `Pop | Timestamp | Villager Assignment / Action | Food Villagers Breakdown (Sheep / Boar / Deer/Chk / Berries / Farms / Total F) | Other Vils (W/G/S) | Resource Bank (F/W/G/S) | Notes / Buildings`.
   - **Age-Up Transition Reallocations & Queues**
   - **Steady-State Target Summary & Rot/Efficiency Telemetry**
3. **RTS Overlay Compatible JSON (`.json`):**
   - Follows the `RTS_Overlay` / `AoE Overlay` schema (`name`, `civilization`, `author`, `source`, `description`, `build_order` array of `{villager_count, age, resources: {wood, food, gold, stone}, notes}` using `@category/icon@` asset tags).
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
| **Lumberjack** (Base) | `0.3900` | `23.40` | `10` | `-1%` every `15s` (`-4%/min`); refresh LC at `60%` |
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
| **Sheep** | `8` | `100 F` | `0.25 F/s` | `0.33 F/s` | `6` (max `8`) | `88.8 F` (`11.2 F` rot) | `44.8 s` |
| **Boar** | `2` | `340 F` | `0.40 F/s` | `0.41 F/s` | `7` (max `9`) | `298.4 F` (`41.6 F` rot) | `104.0 s` |
| **Deer** | `3` | `140 F` | `0.25 F/s` | `0.41 F/s` | `4` (max `6`) | `121.5 F` (`18.5 F` rot) | `74.1 s` |
| **Chicken** | `6–8` | `75 F` | `0.125 F/s` | `0.33 F/s` | `2` (max `4`) | `63.1 F` (`11.9 F` rot) | `95.5 s` |
| **Berry Bush** | `6` | `125 F` (`750 F` tot) | `0.00 F/s` | `0.31 F/s` | `4` | `125.0 F` (`0 F` rot) | `~100.8 s/bush` |
| **Farm (Base)** | — | `175 F` | `0.00 F/s` | `0.3383 F/s` | `1` | `175.0 F` | `517.3 s` |

### 2.3 Multi-Villager Construction Speed
When $n$ villagers construct a building with single-villager build time $t$:
$$T(n) = \frac{3 \cdot t}{n + 2}$$
