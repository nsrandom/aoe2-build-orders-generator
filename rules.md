# AoE2:DE Build Order Generation Rules & Assumptions

This document is the authoritative specification for calculating, simulating, and exporting *Age of Empires II: Definitive Edition* build orders in this project. Output formatting is specified in [`output.md`](output.md).

The only machine-readable copy of these parameters is `RuleConfig` and the data tables in [`scripts/aoe2_data.py`](scripts/aoe2_data.py). Each field there cites its rule number (e.g. `# rule 3.4`); when a rule changes here, change it there too. Build scripts read values from `RuleConfig` / `aoe2_data` instead of hard-coding them, and override per build with `dataclasses.replace(RuleConfig(), ...)`. Build pages and code cite rules by number (e.g. "rule 3.6").

**Status tags**
- **[USER]**: set or confirmed by Asif.
- **[PROPOSED]**: default suggested by the model; in force until confirmed or changed.
- **[DATA]**: game data, from `aoe2-de-tools` or verified against the [AoE2 wiki](https://ageofempires.fandom.com/) / official patch notes (update numbers cited where relevant).

All times are in-game seconds.

---

## 0. Objective & Process

0.1 **[USER]** **Objective:** earliest Castle Age click with no idle TC (other than the 5 s pre-click buffer, rule 5.1), then villager efficiency. When a request states a goal, that goal comes first and these are the tie-breakers.

0.2 **[USER]** When there is an interesting trade-off or doubt about what to optimise, ask. When two significantly different approaches exist, produce both.

0.3 **[USER]** Allowances given in a specific request (e.g. "ranges may idle after 12 archers for a faster Castle Age") apply to that build only and are listed on its page.

0.4 **[USER]** Rule violations found in the simulation are fixed or explicitly explained next to the build order — never delivered silently.

## 1. Scope & Starting Conditions

1.1 **[USER]** Default map is **Arabia**; other maps are named in the request. **[PROPOSED]** 1v1, no opponent interference (no raids, no laming).

1.2 **[DATA]** Start: 200 food, 200 wood, 100 gold, 200 stone; 3 villagers + 1 Scout Cavalry; pop 4/5 (TC provides 5). Civ-specific starts override this (§9).

1.3 **Arabia** home resources:
- **[DATA]** 8 sheep (4 under the TC, 2 pairs just outside TC line of sight), 6 berry bushes (125 F each), 2 wild boar (340 F), 1 seven-tile and 2 smaller gold mines, 1 five-tile and 1 four-tile stone mine. Small hunt is **2–4 deer** or **6–8 wild chickens**, 50/50 (update 141935). A further group of 3 deer spawns much farther away.
- **[USER]** The scout finds 2 more sheep at **1:30** and 2 more at **2:30**.
- **[USER]** Unless a request specifies a deer map, default to a **chicken map** designed for **6 chickens on a mill**, also checked with 8 (rule 8.3).

1.4 **Arena:** **[USER]** default to **6 chickens on a mill** (checked with 8, rule 8.3; Arena chicken map has **8** wild chickens **[DATA]**, 3 deer on deer maps). **[PROPOSED]** Other home resources and sheep timings as on Arabia.

1.5 **[USER]** **Opening:** at `0:00` the 3 starting villagers build 2 houses (2 villagers on house 1 → 18.75 s, 1 villager on house 2 → 25 s), then go to sheep under the TC, paying only the **5 s return walk**. The TC queues villagers from `0:00`.

## 2. Walking

2.1 **[USER]** Sending a villager from work to build a **house**: **5 s each way** (10 s round trip).

2.2 **[USER]** Any **other building** (barracks, range, stable, blacksmith, market, castle, monastery, university, siege workshop…): **10 s each way** (20 s round trip).

2.3 **[USER]** Several buildings in a row by the same villager(s): **0 s** walking between them.

2.4 **[USER]** TC ↔ woodline, gold, stone, berries, or chickens: **15 s one way**. New villagers walk this from the TC to their rally target.

2.5 **[USER]** A villager who walks out to build a drop-off camp (lumber camp, mining camp, mill) pays only the one-way walk (2.4) plus the build time, then gathers there with no further walk.

2.6 **[USER]** Remote site ↔ remote site (wood → gold, old lumber camp → new one): **15 s one way**.

2.7 **[USER]** Switching between food sources under the TC (sheep, boar, pushed deer, farms around the TC), including placing a farm around the TC: **2 s**.

2.8 **[USER]** Switching between under-TC food and a **TC straggler tree** (100 W each): **3 s**.

2.9 **[USER]** Luring a boar: **15 s each way** (30 s without gathering).

2.10 **[USER]** **Forward building** (castle drop, forward base): forward villagers walk the build's forward distance one way (default **60 s**, set per build and stated on its page) and wait there until they can build. Waiting counts as villager idle time.

2.11 **[DATA]** Villager speed 0.8 tiles/s. Wheelbarrow and Hand Cart add +10 % speed each; all walks in this section shorten accordingly.

## 3. Gathering

3.1 **[DATA]** Raw work rates (per second, excluding walking) and carry capacity are in §11.1. **Wild chickens are huntables**: hunter rate 0.41/s, carry 35.

3.2 **[USER]** **Effective rate** = carry ÷ (carry ÷ work rate + drop-off round trip), with these round trips:

| Source | Round trip | Fresh effective rate |
| :--- | :---: | :---: |
| Sheep, boar, pushed deer (under TC) | 1.5 s | sheep 18.9/min, boar & deer 24.2/min |
| Berries (with mill) | 2.5 s | 17.3/min |
| Gold / stone (with mining camp) | 2.5 s | gold 20.8/min, stone 19.8/min |
| Wood (fresh lumber camp) | 3.75 s | 20.4/min |
| TC straggler trees **[PROPOSED]** | 2.5 s | 21.3/min |
| Deer with a mill | 3 s | 23.8/min |
| Chickens with a mill | 2.5 s | 23.9/min |
| Long-distance to the TC (no camp; gold, stone, chickens) | 30 s (rule 2.4 both ways) | gold 10.7/min, chickens 18.2/min |

Farm rates already include walking (§11.1).

3.3 **[USER]** **Long-distance gathering** (no drop-off camp) is allowed whenever it makes the build more efficient (e.g. 50–70 gold for Loom or Dravidian Men-at-Arms without spending 100 W on a mining camp, or hunting 4–6 chickens). Each load pays the 30 s round trip (3.2).

3.4 **[USER]** **Wood efficiency decay & camp refresh:**
- Efficiency drops **1 % every 20 s** after a lumber camp is completed, to a floor of **60 %**. It multiplies the effective wood rate.
- A new lumber camp resets efficiency to 100 % **only for the woodcutters working at it**; moving there costs the 15 s site-to-site walk (2.6).
- A camp is replaced once it is down to **60–65 %** (about 700–800 s after it was built).
- **Wood priority:** replacing a camp is the **lowest priority** for wood. It only uses wood left after every waiting building, queued research, house, and farm a farmer is waiting for. It does not hold back unit production.
- **Density:** aim for 7–8 woodcutters per camp; when expanding to 9+, add another camp (subject to the wood priority rule).

3.5 **[DATA]** Killed animals rot continuously, including while being gathered: sheep and deer 0.25 F/s, boar 0.4 F/s, wild chickens 0.125 F/s. Since update 153015, food from animals killed by military or buildings (e.g. the TC) no longer spoils and can be gathered. Jurchens' hunt doesn't rot.

3.6 **[USER]** **Minimise rot:** slaughter only one animal of a type at a time unless too many villagers are on the current one. Villagers per carcass:
- **Sheep:** 6 (never more than 7)
- **Boar:** 7–8 (9 or fewer; up to 10 during age-up transitions)
- **Deer:** 4 (never more than 7)
- **Chicken:** 2 (3–4 on a milled patch)

A little extra rot is acceptable if it buys efficiency elsewhere. **[PROPOSED]** The next animal is opened 2 s before the current one runs out.

3.7 **[USER]** **Boar:**
- When a boar arrives under the TC, **6–8 villagers garrison the TC for 5 s** to shoot it down (30–40 villager-seconds lost per boar).
- Never slaughter a new sheep while a boar carcass is open. Shepherds finishing their sheep switch to the boar. If only a little food remains on the current sheep when the boar goes down, put 6+ villagers on the boar right away and let one villager finish the sheep.
- **[PROPOSED]** The second boar is lured by one boar hunter, timed to arrive as the first runs out.

3.8 **[USER]** **Deer (when a request specifies a deer map):** taken in Dark Age unless the request says to skip them.
- The scout pushes deer one at a time, starting once **9 villagers are on food under the TC**. The first deer arrives **30 s** later, then one every **35 s**.
- Deer are **only pushed in Dark Age**: after the Feudal click the scout is busy.
- A build need not use every deer; it pushes as many as fit before the click (at least one, unless the request skips deer).
- Pushed deer are gathered under the TC (round trip per 3.2; switching per 2.7).

3.9 **[USER]** **Chickens (default hunt map):** can't be pushed; hunted in Dark Age unless the request skips them. Default to **6 chickens on a mill** (also checked with 8 under rule 8.3). For Feudal builds, prefer milling chickens before berries since chicken food collects faster (23.9 vs 17.3/min). For Fast Castle builds, if wood allows both mills in Dark Age (chickens + berries), take both; otherwise choose whichever makes more sense.

3.10 **[USER]** **Farms:** 60 W, 15 s build (one farmer per farm), require a completed mill (Khmer excepted for placing farms; a mill is always required to unlock Horse Collar and farm upgrades). Farms go **around the TC first** (**[PROPOSED]** 8 farms), then around mills. **[PROPOSED]** Reseeding costs 60 W and 15 s; a farmer with no wood to reseed stands idle. Farm food: 175 (+75 Horse Collar, +125 Heavy Plow, +175 Crop Rotation) **[DATA]**.

3.11 **[DATA]** Villagers don't lose carried resources when re-tasked; they drop them when they finish building a drop-off camp or farm.

3.12 **[PROPOSED]** When a food source runs out, its villagers move to the next source in the build's fallback list and pay the walk.

## 4. Construction & Population

4.1 **[DATA]** Build times (1 villager) and costs are in §11.3. With *n* builders: build time = base × 3 ÷ (*n* + 2).

4.2 **[USER]** Building costs leave the bank when the builder is sent. Unit and tech costs leave the bank when production starts.

4.3 **[DATA]** House +5 pop, TC +5, castle +20, cap 200. **[USER]** A unit needs free population when its training **starts**; the unit in training counts.

4.4 **[USER]** **House timing:** start houses so **2–3 villagers of room** remain when they finish (just in time is acceptable in a tight build). Add 1 to the threshold for each producing military building and each extra TC. Houses come before units: while a house waits for wood, military buildings don't spend its 25 W.

4.5 **[USER]** Waiting builds are paid **first come, first served**: a later, cheaper building doesn't take the wood a waiting building needs. Builds marked *priority* (e.g. a 2nd archery range) also hold back military production until placed. Lumber camp refreshes are the opposite (3.4).

4.6 **[DATA]** **Age-up requirements:**
- Feudal needs 2 of barracks / mill / lumber camp / mining camp / dock (houses don't count).
- Castle needs 2 of archery range / stable / blacksmith / market.
- Imperial needs 2 Castle Age buildings or a castle.

Archery range, stable, blacksmith and market need Feudal Age, so they can't be placed during the Feudal age-up.

## 5. Town Center & Production

5.1 **[USER]** The TC may be idle for **at most 5 s** before an age-up click (it doubles as a buffer for imperfect play). Any other TC idle (housed, out of food, waiting for Loom gold) is a violation.

5.2 **[USER]** Outside that window the TC produces continuously: villagers (25 s, 50 F, paid as each starts) or research (Loom, age-ups, TC eco techs).

5.3 **[USER]** The TC may hold for up to 5 s when the next age-up will be affordable within that time, instead of starting a villager that would delay the click by 25 s.

5.4 **[PROPOSED]** A tech queued at the TC starts as soon as the current villager finishes. A tech marked "when affordable" doesn't idle the TC: villagers continue until it is affordable. With several TCs, each produces continuously; a TC tech goes to whichever TC is free first.

5.5 **[PROPOSED]** "Continuous production" from a military building means it is never idle while it has the resources. A build may mark lower-priority production ("from leftover resources") that only starts when a reserve for higher-priority queues remains.

5.6 **[USER]** "Click at N pop" means the age-up starts right after the unit that makes pop N (villagers + scout + military) comes out.

## 6. Ages, Techs & Defaults

6.1 **[DATA]** Age-up and tech costs/times are in §11.4.

6.2 **[USER]** **Loom** before the Feudal click on Arabia (except safe Fast Castle builds, where it may be delayed). On Arena it's deferred. Other maps: as stated in the request.

6.3 **[USER]** **Eco upgrade defaults:** Double-Bit Axe on reaching Feudal Age (**[PROPOSED]** tight Fast Castle builds may defer it until after clicking Castle Age when Feudal lasts only ~50 s and wood is needed for Market + Blacksmith); Bow Saw on reaching Castle Age; Horse Collar before heavy farming (unless executing a tight all-in).

6.4 **[USER]** **Ballistics priority:** once a build has **20+ ranged units** (archers, crossbows, skirmishers, cavalry archers, elephant archers, Genoese, …), build a University and research Ballistics ahead of extra production buildings, late TCs, or secondary upgrades, unless another explicit high-priority goal is active (imminent age-up, Castle Age TC drops).

6.5 **[USER]** When a Castle Age build ramps military first (e.g. to 50+ units), scale extra military buildings early, then switch priority to Imperial Age, idling extra military buildings if needed, so Imperial is reliably reached **before 40:00**.

## 7. Market

7.1 **[USER]** Using the Market occasionally to balance stockpiles is fine (hitting age-up clicks, castle/TC drops, key upgrades without idling production).

7.2 **[DATA]** **Trading model** (shared global prices; other players' trades not modelled):
- Base exchange rates per 100: wood 100, food 115 (update 125283), stone 130.
- Selling gives 70 % of the rate and buying costs 130 % (30 % fee; Guilds 15 %, Saracens 5 %). Starting prices: sell 100 wood / food / stone for **70 / 81 / 91** gold; buy for 130 / 150 / 169.
- Each 100 traded moves that resource's rate by **2** (down when selling, up when buying), with a minimum rate of 20 (sell 14 / buy 26).

7.3 **[DATA]** **Relics:** a Relic garrisoned in a Monastery or Fortified Church generates **0.5 gold/s** (30 gold/min).

## 8. Execution, Simplicity & Robustness

8.1 **[USER]** **Tight early precision vs. macro later:** humans can follow a villager-by-villager order for only the first ~20–30 villagers (Dark Age + Feudal transition for normal builds; through the Castle click for Fast Castle).
- **Combined same-resource steps:** consecutive villagers to the same resource, including the first one building a camp or house, are combined into one step (e.g. "3 vils to wood after the 1st builds a lumber camp").
- **Macro phases** (Feudal+ for normal builds; Castle+ for Fast Castle) use priority-loop instructions, e.g. "Make vils continuously → new vils to stragglers & seed farms every 60 W, while producing X from leftover resources until <criteria>".

8.2 **[USER]** **Macro efficiency buffer:** macro phases apply **92 %** effective gather efficiency in Feudal and **90 %** in Castle Age+, plus safety reserves before major clicks/buildings. **[PROPOSED]** For Fast Castle builds, the macro phase starts in Castle Age (so Dark Age + Feudal transition run at 100 %, Castle+ at 90 %). This absorbs transition friction, bumping, farm placement delays and army micro.

8.3 **[USER]** **Late-command check** for the precise phases (Dark Age and Feudal), run before delivery:
- every command 3 s late;
- 20 runs with each command late by a random 0–5 s;
- on chicken maps, also 8 chickens instead of 6.

Commands at `0:00` (opening houses, villager queue) are always on time. A scenario passes when the TC is never housed, extra-TC idle is at most 5 s, and every age-up click is at most 15 s later than planned. Failures are fixed or explained next to the build (0.4).

8.4 **[USER]** **Resource float cap:** unless banking for a concrete target (age-up, castle drop, power-spike tech), avoid floating more than **~500–1,000** of any resource. Spend surplus on extra production buildings, eco/military upgrades, extra TCs, villager rebalancing, or Market trades (§7).

## 9. Civilisation Bonuses

9.1 **[USER]** Civ bonuses are researched against the current patch when a civ is first requested and encoded in the simulator (cost, gather-rate, carry, train-time, age-up and start modifiers), with sources noted. The civ notes in §11.1 are a starting point, not a substitute.

## 10. Output

10.1 **[USER]** See [`output.md`](output.md). In summary, each build lives in `builds/<build_slug>/` with:
- build-specific `sim_<build_slug>.py` and `generate_<build_slug>.py`;
- an HTML report (`<build_slug>.html`) with a tab per variant, timeline tables split by phase, compressed same-resource and macro rows, and a strategy comparison chart;
- an RTS Overlay JSON per variant, where every step satisfies `sum(resources.values()) == villager_count`.

---

## 11. Reference Data

### 11.1 Villager Work Rates & Carry Capacity **[DATA]**
Raw work rates exclude walking; apply rule 3.2 for effective rates (farms excepted).

| Role | Rate (res/s) | Rate (res/min) | Carry | Notes / civ examples |
| :--- | :---: | :---: | :---: | :--- |
| **Hunter** (boar, deer, wild chicken) | 0.41 | 24.6 | 35 | Goths: +15 carry, hunt lasts 20 % longer |
| **Shepherd** | 0.33 | 19.8 | 10 | Britons +25 % |
| **Forager** | 0.31 | 18.6 | 10 | Portuguese: +0.33 wood per food |
| **Farmer** (base) | 0.3383 | 20.3 | 10 | Includes farm walking; farms produce at most 0.4 F/s |
| **Farmer** (Heavy Plow) | 0.3533 | 21.2 | 11 | |
| **Farmer** (Wheelbarrow) | 0.3838 | 23.0 | 13 | |
| **Farmer** (Wheelbarrow + Heavy Plow) | 0.3860 | 23.2 | 14 | |
| **Farmer** (Hand Cart) | 0.4000 | 24.0 | 20 | Farm production cap reached (+1 w/ Heavy Plow) |
| **Lumberjack** | 0.39 | 23.4 | 10 | Double-Bit Axe & Bow Saw +20 % each, Two-Man Saw +10 %; decay per 3.4 |
| **Gold miner** | 0.38 | 22.8 | 10 | Gold Mining & Gold Shaft Mining +15 % each |
| **Stone miner** | 0.36 | 21.6 | 10 | Stone Mining & Stone Shaft Mining +15 % each |

Carry upgrades: Wheelbarrow +27 % (rounded up), Hand Cart brings the total to +100 % of base (10 → 13 → 20; hunters 35 → 44 → 66). Heavy Plow +1 farmer carry.

### 11.2 Natural Food Sources & Rot **[DATA]**
With *N* villagers at rate *r* on a carcass decaying at *d*: duration $T = \frac{F_0}{N r + d}$, net food $F_{\text{net}} = F_0 \cdot \frac{N r}{N r + d}$.

| Source | Arabia count | $F_0$ | Decay $d$ | Rate $r$ | Ideal $N$ | Net at ideal $N$ | Duration |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Sheep** | 8 | 100 | 0.25 | 0.33 | 6 (max 7) | 88.8 (11.2 rot) | 44.8 s |
| **Boar** | 2 | 340 | 0.40 | 0.41 | 7–8 (max 9; 10 trans.) | 303.2 @8 (36.8 rot) | 92.4 s |
| **Deer** | 2–4 | 140 | 0.25 | 0.41 | 4 (max 7) | 121.5 (18.5 rot) | 74.1 s |
| **Wild chicken** | 6–8 | 75 | 0.125 | 0.41 | 2 (3–4 milled) | 65.1 (9.9 rot) | 79.4 s |
| **Berry bush** | 6 | 125 | 0 | 0.31 | — | 125 | — |
| **Farm** (base) | — | 175 | 0 | 0.3383 | 1 | 175 | 517 s |

(Carcass figures assume continuous work under the TC; drop-off round trips per 3.2 are additional.)

### 11.3 Buildings **[DATA]**

| Building | Cost | Time (1 villager) |
| :--- | :--- | :---: |
| House | 25 W | 25 s |
| Farm | 60 W | 15 s |
| Mill / Lumber Camp / Mining Camp | 100 W | 35 s |
| Blacksmith | 150 W | 40 s |
| Barracks / Archery Range / Stable | 175 W | 50 s |
| Market | 175 W | 60 s |
| University | 200 W | 60 s |
| Town Center | 275 W, 100 S | 150 s |
| Castle | 650 S | 200 s |

### 11.4 Ages & Technologies **[DATA]**

| Item | Cost | Time |
| :--- | :--- | :---: |
| Feudal Age | 500 F | 130 s |
| Castle Age | 800 F, 200 G | 160 s |
| Imperial Age | 1000 F, 800 G | 190 s |
| Loom | 50 G | 25 s |
| Wheelbarrow | 175 F, 50 W | 75 s |
| Hand Cart | 300 F, 200 W | 55 s |
| Double-Bit Axe | 100 F, 50 W | 25 s |
| Bow Saw | 150 F, 100 W | 50 s |
| Horse Collar | 75 F, 75 W | 20 s |
| Heavy Plow | 125 F, 125 W | 40 s |
| Gold Mining / Stone Mining | 100 F, 75 W | 30 s |
| Ballistics | 300 W, 175 G | 60 s |
| Man-at-Arms upgrade | 100 F, 40 G | 40 s |

---

## Open items

1. **TC-killed carcass rot:** update 153015 confirms the food is gatherable, but not whether it then decays. The garrison method (3.7) assumes normal rot from the kill.
