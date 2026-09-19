# Slot B late post-43 device round (2026-09-19)

Round: `MAINLINE_V2_R3_SLOT_B_LATE_POST43_DEVICE_ADVANCE`. Device: Xiaomi
Mi 10S (thyme / M2102J2SC) serial `41a5627b`, operated serially by the main
agent from healthy Android A. Final gate:
**`R3_SLOT_B_LATE_POST43_INDEX55_SHIFT_NOT_OBSERVED`**.

## Pair result

| Member | Boot identity (frozen) | Behavior | total_s |
|---|---|---|---|
| `POST43_8` | `00f8bdbb…73a26` (37380096) | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 47.888133875 |
| `POST43_1` | `c9fb8d39…e8ff8cc` (37380096) | `AUTOMATIC_FASTBOOT_RETURN`, retry 7→6 | 47.845147208 |

`PAIR_DELTA=-0.042986667s` vs expected `-7.000000000s` (`PAIR_ERROR=+6.957013333s`)
→ **`SHIFT_NOT_OBSERVED`** (`late_post43_checkpoint_shift_not_observed=YES`).
The 8s/1s delay-constant difference did not manifest; the probe checkpoint
shift at index 55 was not observed. Per the frozen evidence semantics this
records ONLY the shift absence: `GENPD_DEBUG_INIT_ENTRY=NOT_PROVEN` with no
entry and no non-entry claim licensed; `TARGET_NOT_REACHED` is never written.
`LATEST_PROVEN_LATE_INDEX=43` unchanged; the working diagnostic branch moves
from `43..86` to **`43..55`**; the next candidate is **index 49 `bert_init`**
(index 60 is forbidden on this branch).

## Protocol compliance

Both members: full-SHA identity gate before any fastboot interaction, one
RAM-only `fastboot boot` each from the authorized bootloader session, timing
only from observer `total_s`, `NO_RETURN_WITHIN_120S` did not occur. Current B
16-chain hashes and the P15 prefix (`133e063b…87d34`) MATCH pre / between /
post; Android A restored healthy after each member (slot `_a`, `4.19.157-perf-g9d90dd04aa7c`);
`PARTITION_WRITES=0`, `SLOT_A_WRITTEN=NO`, USB `FROZEN`.
`late_post438`/`late_post431` are rerun-FORBIDDEN.

## Evidence

`artifacts/slot-b-late-post43-device-20260919/device-round/` — host logs,
observer `result.json`/`events.json` per member, partition snapshots, set-active
records, `final-report.txt`. Chain: public `35435068388` @ `c6da8e8`, private
pack `35435526523`, reverify `35435680009`, freeze `2b793bc`+`a3f3b78`, observer
fixtures `35436961277`.

## Next stage

`MAINLINE_V2_R3_SLOT_B_LATE_POST49_CHILD_GATES_THEN_DEVICE` — child index 49
`bert_init` (`0xffff800081b7017c`, 408B, window 404 CFG-forced) must complete
private pack, independent reverify, observer fixtures and full identity freeze
(all GHA) before the same-round device split pair `POST49_8 → POST49_1`.
