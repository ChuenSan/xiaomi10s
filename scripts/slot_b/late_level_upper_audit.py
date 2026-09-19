#!/usr/bin/env python3
"""Independent CFG/geometry auditor for the upper child (~index 64) of the
level-7 late initcall span, plus the level-7 completion boundary bracket.

Round: MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION (Slot B, Sub Agent C).
This module deliberately shares no code with the selection machinery it
cross-checks: every gate below is re-derived from the frozen GHA artifacts
(late-table.json, audit.json, window.txt) and from sha-pinned GHA-produced
binaries parsed with an internal minimal ELF reader.

Evidence classes used throughout:
  FROZEN_ARTIFACT   - value taken from a GHA-produced JSON/text artifact.
  LOCAL_BINARY      - value derived here from sha-pinned GHA-produced binaries
                      (payload.bin / bundle Image / bundle vmlinux); the sha is
                      verified against the GHA-recorded value before use.
  PENDING_AUTHORITATIVE_MAP - not locally decidable; the authoritative GHA map
                      must confirm it before any device round.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen constants (round MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION)
# ---------------------------------------------------------------------------

TEXT_VA = 0xFFFF800080000000
INITCALL7_START_VA = 0xFFFF800081D0C2D8
INITCALL_END_VA = 0xFFFF800081D0C430
LATE_SPAN_COUNT = 86
NOMINAL_UPPER_CHILD_INDEX = 64
MIN_INLINE_WINDOW = 56            # 4B paciasp + 52B proven no-daifset core
ULTRACOMPACT_WINDOW = 60          # 4B paciasp + 56B proven daifset core
STRONG_TOLERANCE_S = 1.0
EXPECTED_PAIR_DELTA_S = -7.0

# Frozen probe cores (re-declared from the frozen facts, not imported).
# 56B ultracompact core file: 14 words; word 2 (0xD37DF12A) is the 8s delay.
# A function-entry probe of window 60 = preserved paciasp (the target's own
# entry word) + the 56B core, so the delay lands at probe word 3 -> pair diff
# bytes [window+13, window+15), matching the frozen index-0 diff
# [0x1b32085, 0x1b32087). A window-56 function-entry probe = paciasp + the
# 52B no-daifset core (the 56B core minus its leading word), delay at probe
# word 2 -> pair diff [window+9, window+11).
ULTRACOMPACT_CORE56_WORDS = (
    0xD5034FDF, 0xD53BE009, 0xD37DF12A, 0xD53BE02B, 0xD5033FDF, 0xD53BE02C,
    0xCB0B018D, 0xEB0A01BF, 0x54FFFF83, 0x52800120, 0x72B08000,
    0xD4000003, 0xD503205F, 0x17FFFFFF,
)
SUBSYS52_CORE_WORDS = ULTRACOMPACT_CORE56_WORDS[1:]
DELAY_PROBE_WORD = {60: 3, 56: 2}


def pair_diff(window_offset: int, window: int):
    """DELAY_CONSTANT_ONLY 2-byte diff range for a probe at window_offset."""
    word = DELAY_PROBE_WORD[window]
    return (window_offset + 4 * word + 1, window_offset + 4 * word + 3)

PACIASP = 0xD503233F

# Boundary bracket (frozen from run 35414669247 / artifact audit.json).
LATE_COMPLETE_WINDOW = (0x1B3113C, 0x1B31174)
WAIT_COMPLETE_WINDOW = (0x1B31140, 0x1B31174)
CALLER_SPAN = (0x1B3103C, 0x1B311A8)
COLD_PATH_VA = 0x1B31174
CALLER_PAIR_DIFF = (0x1B31145, 0x1B31147)
WAITENTRY_TOTALS = {"8": 45.212251791, "1": 48.412371375}
WAITENTRY_PAIR_DELTA_S = 3.200119584

# GHA-recorded artifact identities (FROZEN_ARTIFACT).
FROZEN_BUNDLE_ELF_SHA = "295bfdb12184052a79c1aea35ce4a93a5833c42bdb7b4bd9173973312ade00ff"
FROZEN_BUNDLE_IMAGE_SHA = "43fb1c9128bdf37a2a77eb88cfff234381340b098ebf1aea1eabb2741180cebb"
LEVEL7_DEVPROBE8_PAYLOAD_SHA = "92794991a6f1a0bd100262a5174e0adf6f29670f4ba64b8b852ba232d5e684df"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise AuditError(message)


class AuditError(ValueError):
    pass


# ---------------------------------------------------------------------------
# ARM64 branch decoding (independent implementation)
# ---------------------------------------------------------------------------

def _sx(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


BRANCH_KINDS = ("B", "BL", "B.cond", "CBZ", "TBZ")


def branch_target(word: int, pc: int):
    """Decode a direct/PC-relative branch; return (target, kind) or None."""
    if word & 0x7C000000 == 0x14000000:
        return pc + _sx(word & 0x03FFFFFF, 26) * 4, ("BL" if word >> 31 else "B")
    if word & 0xFF000010 == 0x54000000:
        return pc + _sx((word >> 5) & 0x7FFFF, 19) * 4, "B.cond"
    if word & 0x7E000000 == 0x34000000:
        return pc + _sx((word >> 5) & 0x7FFFF, 19) * 4, "CBZ"
    if word & 0x7E000000 == 0x36000000:
        return pc + _sx((word >> 5) & 0x3FFF, 14) * 4, "TBZ"
    return None


# ---------------------------------------------------------------------------
# Context: authoritative map assembled from artifacts
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    index: int
    symbol: str
    target_va: int
    entry_va: int
    entry_image_offset: int
    entry_word: int
    relative: int
    aliases: tuple


@dataclass
class AuthoritativeMap:
    """Geometry inputs. Byte/image-offset coordinates: image_off = va - TEXT_VA."""
    image: bytes
    image_evidence: str
    image_sha_expected: str | None
    exec_ranges: tuple                      # ((lo, hi), ...) image offsets
    symbol_vas: tuple                       # sorted VAs of every named symbol
    symbol_st_size: dict                    # va -> st_size (FUNC symbols)
    reloc_sites: tuple                      # sorted image offsets
    ex_table_insns: tuple                   # sorted image offsets (insn addrs)
    alt_ranges: tuple                       # ((orig_lo, orig_hi), ...)
    absent_rewrite_sections: tuple = ("__jump_table", ".static_call_sites", ".kcfi_traps")
    patched_windows: tuple = ()             # known probe windows already in image
    late_table: tuple = ()                  # Candidate records (86)
    source_tree: Path | None = None         # optional linux tree for macro check
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def verified(self) -> "AuthoritativeMap":
        if self.image_sha_expected is not None:
            require(digest(self.image) == self.image_sha_expected,
                    "IMAGE_SHA_MISMATCH")
        return self

    def extent(self, va: int) -> int | None:
        i = bisect.bisect_right(self.symbol_vas, va)
        return (self.symbol_vas[i] - va) if i < len(self.symbol_vas) else None

    def function_size(self, va: int) -> int | None:
        return self.symbol_st_size.get(va) or self.extent(va)

    def interior_symbols(self, lo_off: int, hi_off: int):
        lo, hi = TEXT_VA + lo_off, TEXT_VA + hi_off
        return [v for v in self.symbol_vas if lo < v < hi]

    def relocs_in(self, lo_off: int, hi_off: int):
        i = bisect.bisect_left(self.reloc_sites, lo_off)
        out = []
        while i < len(self.reloc_sites) and self.reloc_sites[i] < hi_off:
            out.append(self.reloc_sites[i]); i += 1
        return out

    def ex_table_in(self, lo_off: int, hi_off: int):
        i = bisect.bisect_left(self.ex_table_insns, lo_off)
        out = []
        while i < len(self.ex_table_insns) and self.ex_table_insns[i] < hi_off:
            out.append(self.ex_table_insns[i]); i += 1
        return out

    def alts_in(self, lo_off: int, hi_off: int):
        return [(a, b) for a, b in self.alt_ranges if a < hi_off and b > lo_off]

    def literal_index(self):
        """Sorted image offsets of 8-byte aligned absolute literals whose value
        is a plausible VA (TEXT_VA <= value < TEXT_VA + len(image)). One pass,
        cached: only these can point into any candidate window."""
        if "literal_index" not in self._cache:
            n = len(self.image) // 8 * 8
            vals = []
            for i, (val,) in enumerate(struct.iter_unpack("<Q", self.image[:n])):
                if TEXT_VA <= val < TEXT_VA + len(self.image):
                    vals.append(val - TEXT_VA)
            self._cache["literal_index"] = tuple(sorted(vals))
        return self._cache["literal_index"]

    def literals_in(self, lo_off: int, hi_off: int):
        idx = self.literal_index()
        i = bisect.bisect_left(idx, lo_off + 1)
        out = []
        while i < len(idx) and idx[i] < hi_off:
            out.append(idx[i]); i += 1
        return out

    def branch_index(self):
        """Cached full-image (src_off, tgt_off, kind) branch list."""
        if "branch_index" not in self._cache:
            self._cache["branch_index"] = scan_branches(
                self, exclude_sources=self.patched_windows)
        return self._cache["branch_index"]


def scan_branches(ctx: AuthoritativeMap, exclude_sources=()) -> list:
    """Every (src_off, tgt_off, kind) branch word in the executable ranges."""
    skip = sorted(exclude_sources)
    rows = []
    image, ranges = ctx.image, ctx.exec_ranges
    n_words = len(image) // 4
    words = list(struct.unpack_from(f"<{n_words}I", image, 0))
    for lo, hi in sorted(ranges):
        off = max(0, lo)
        end = min(len(image), hi) - 3
        while off < end:
            while skip and skip[0][1] <= off:
                skip.pop(0)
            if skip and skip[0][0] <= off:
                off = skip.pop(0)[1]
                continue
            word = words[off // 4]
            decoded = branch_target(word, TEXT_VA + off)
            if decoded is not None:
                rows.append((off, decoded[0] - TEXT_VA, decoded[1]))
            off += 4
    return rows


# ---------------------------------------------------------------------------
# Gate evaluator
# ---------------------------------------------------------------------------

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING_AUTHORITATIVE_MAP"


@dataclass
class Gate:
    name: str
    status: str
    detail: str = ""
    evidence: str = "LOCAL_BINARY"


@dataclass
class Verdict:
    candidate: Candidate
    window: int | None
    core: str | None
    function_size: int | None
    gates: list = field(default_factory=list)
    derived_window: int | None = None
    topology: dict = field(default_factory=dict)

    @property
    def registration(self):
        """Source-level registration status (locally checkable only with a
        pinned source tree; otherwise PENDING_AUTHORITATIVE_MAP)."""
        gate = next((g for g in self.gates if g.name == "REGISTRATION"), None)
        return gate.status if gate else PENDING

    @property
    def passed(self):
        return self.window is not None and all(g.status == PASS for g in self.gates)

    @property
    def geometry_passed(self):
        """Selection passability: geometry gates must PASS; a PENDING
        registration (no pinned source tree) is acceptable because the
        authoritative CI source-contract gate owns it. A FAIL blocks."""
        return self.window is not None and all(
            g.status == PASS or (g.name == "REGISTRATION" and g.status == PENDING)
            for g in self.gates)

    def reasons(self):
        return [f"{g.name}={g.status}:{g.detail}" for g in self.gates
                if g.status != PASS]

    def as_dict(self):
        return {"index": self.candidate.index, "symbol": self.candidate.symbol,
                "target_va": hex(self.candidate.target_va),
                "function_size": self.function_size, "window": self.window,
                "core": self.core, "derived_window": self.derived_window,
                "passed": self.passed, "geometry_passed": self.geometry_passed,
                "registration": self.registration,
                "gates": [vars(g) for g in self.gates],
                "topology": self.topology, "reasons": self.reasons()}


def core_for_window(window: int):
    """Proven core that fits a window: the 56B ultracompact core fits any
    4-aligned window >= 60 (NOP padded); the 52B no-daifset core fits 56."""
    if window % 4:
        raise AuditError("WINDOW_UNALIGNED")
    if window == MIN_INLINE_WINDOW:
        return "52B_NO_DAIFSET", MIN_INLINE_WINDOW
    if window >= ULTRACOMPACT_WINDOW:
        return "56B_ULTRACOMPACT", ULTRACOMPACT_WINDOW
    raise AuditError("INVALID_WINDOW_FOR_CORE")


def derive_window(function_size: int, internal: list, min_size: int):
    """Closure growth: while a branch source outside the window targets the
    window interior (0 < dst < window), grow to cover that source.
    Mirrors the frozen TARGET_CFG derivation semantics."""
    require(min_size > 0 and min_size % 4 == 0, "INVALID_MIN_PROBE")
    require(function_size >= min_size, "PROBE_LARGER_THAN_TARGET_FUNCTION")
    window = min_size
    while True:
        live = [s for s, d, _ in internal if s >= window and 0 < d < window]
        if not live:
            return window
        grown = max(((s + 4 + 3) & ~3) for s, d, _ in internal
                    if s >= window and 0 < d < window)
        if grown > function_size:
            raise AuditError("CFG_CLOSURE_EXCEEDS_FUNCTION")
        if grown <= window:
            raise AuditError("CFG_WINDOW_DID_NOT_GROW")
        window = grown


def closure_candidates(cand: Candidate, size: int, internal: list,
                       start_window: int):
    """Derivation steps: windows where a surviving branch target lands in the
    closure-sensitive zone (0 < dst < window), with the growth they force."""
    steps = []
    window = start_window
    while window <= size:
        live = [(s, d) for s, d, _ in internal if s >= window and 0 < d < window]
        if not live:
            break
        grown = max(((s + 4 + 3) & ~3) for s, d in live)
        steps.append({"window": window, "grew_to": grown,
                      "surviving": [[hex(TEXT_VA + cand.target_va - TEXT_VA + s),
                                     hex(TEXT_VA + cand.target_va - TEXT_VA + d)]
                                    for s, d in live]})
        window = grown
    return steps


def evaluate(ctx: AuthoritativeMap, cand: Candidate, window: int | None = None,
             branch_index: list | None = None) -> Verdict:
    """Evaluate one candidate configuration. window=None runs the late-level
    selection policy (60B ultracompact preferred, closure growth allowed;
    52B core only when the function cannot hold the 60B window)."""
    size = ctx.function_size(cand.target_va)
    v = Verdict(cand, None, None, size)
    if size is None:
        v.gates.append(Gate("FUNCTION_EXTENT", PENDING,
                            "no symbol extent; authoritative nm map required"))
        return v
    v.gates.append(Gate("FUNCTION_EXTENT", PASS, f"size={size}"))

    if size < MIN_INLINE_WINDOW:
        v.gates.append(Gate("MIN_WINDOW", FAIL,
                            f"function_size={size} < {MIN_INLINE_WINDOW}"
                            " (trampoline forbidden, INLINE only)"))
        return v

    toff = cand.target_va - TEXT_VA
    branches = branch_index if branch_index is not None else ctx.branch_index()
    internal = sorted((s - toff, t - toff, k) for s, t, k in branches
                      if toff <= s < toff + size and toff <= t < toff + size)
    back_edges = [(s, d) for s, d, _ in internal if d < s]
    v.topology = {
        "internal_branches": [[hex(TEXT_VA + toff + s), hex(TEXT_VA + toff + d), k]
                              for s, d, k in internal],
        "back_edges": [[hex(TEXT_VA + toff + s), hex(TEXT_VA + toff + d)]
                       for s, d in back_edges],
    }

    # Core/window policy and closure.
    if window is None:
        if size >= ULTRACOMPACT_WINDOW:
            try:
                window = derive_window(size, internal, ULTRACOMPACT_WINDOW)
            except AuditError as exc:
                v.gates.append(Gate("CFG_CLOSURE", FAIL, str(exc)))
                return v
        else:
            window = MIN_INLINE_WINDOW
        v.derived_window = window
    v.window = window
    try:
        core_name, core_size = core_for_window(window)
    except AuditError:
        v.gates.append(Gate("WINDOW_CORE_FIT", FAIL,
                            f"window={window} matches no proven core"))
        return v
    v.core = core_name

    # G1 window fit / no cross-function overwrite.
    if window % 4 or window < MIN_INLINE_WINDOW or window > size:
        v.gates.append(Gate("WINDOW_FIT", FAIL, f"window={window} size={size}"))
    else:
        v.gates.append(Gate("WINDOW_FIT", PASS, f"window={window} <= size={size}"))
    nxt = ctx.extent(cand.target_va)
    if nxt is not None and toff + window > (cand.target_va - TEXT_VA) + nxt:
        v.gates.append(Gate("NO_CROSS_FUNCTION_OVERWRITE", FAIL,
                            "window passes next symbol boundary"))
    else:
        v.gates.append(Gate("NO_CROSS_FUNCTION_OVERWRITE", PASS,
                            f"window end <= next symbol (+{nxt})" if nxt
                            else "no next symbol (image end)"))

    # G2 entry architecture.
    word0 = struct.unpack_from("<I", ctx.image, toff)[0]
    bti_words = {0xD503241F: "bti", 0xD503245F: "bti c", 0xD503249F: "bti j",
                 0xD50324DF: "bti jc"}
    if word0 == PACIASP:
        v.gates.append(Gate("PACIASP_ENTRY", PASS, "entry=paciasp"))
    else:
        label = f" ({bti_words[word0]})" if word0 in bti_words else ""
        v.gates.append(Gate("PACIASP_ENTRY", FAIL,
                            f"entry word {word0:#x}{label}"))
    v.topology["entry_word"] = hex(word0)
    v.topology["bti"] = word0 in bti_words

    # G3 incoming branches (entry and window interior). All coordinates are
    # image offsets; the function entry is at `toff`.
    incoming_entry = [(s, t, k) for s, t, k in branches
                      if t == toff and not toff <= s < toff + size]
    incoming_interior = [(s, t, k) for s, t, k in branches
                         if toff < t < toff + window and not toff <= s < toff + window]
    v.topology["incoming_entry"] = [[hex(TEXT_VA + s), hex(TEXT_VA + t)]
                                    for s, t, _ in incoming_entry]
    v.topology["incoming_window_interior"] = [[hex(TEXT_VA + s), hex(TEXT_VA + t)]
                                              for s, t, _ in incoming_interior]
    if incoming_entry:
        v.gates.append(Gate("INCOMING_ENTRY_BRANCH", FAIL,
                            str(v.topology["incoming_entry"][:4])))
    else:
        v.gates.append(Gate("INCOMING_ENTRY_BRANCH", PASS, "none"))
    if incoming_interior:
        v.gates.append(Gate("INCOMING_WINDOW_INTERIOR", FAIL,
                            str(v.topology["incoming_window_interior"][:4])))
    else:
        v.gates.append(Gate("INCOMING_WINDOW_INTERIOR", PASS, "none"))

    # G4 CFG closure of the chosen window.
    survivors = [(s, d) for s, d, _ in internal
                 if s >= window and 0 < d < window]
    v.topology["surviving_into_interior"] = [
        [hex(TEXT_VA + toff + s), hex(TEXT_VA + toff + d)] for s, d in survivors]
    preferred = ULTRACOMPACT_WINDOW if size >= ULTRACOMPACT_WINDOW else MIN_INLINE_WINDOW
    if v.derived_window is not None and v.derived_window > preferred:
        v.topology["growth_steps"] = closure_candidates(cand, size, internal,
                                                        preferred)
    if survivors:
        v.gates.append(Gate("CFG_CLOSURE", FAIL,
                            f"surviving branch into window interior at window={window}"))
    else:
        detail = f"window={window} covers all interior-target sources"
        if v.derived_window == window and window > ULTRACOMPACT_WINDOW:
            detail += f" (derived from {ULTRACOMPACT_WINDOW} via back-edge growth)"
        v.gates.append(Gate("CFG_CLOSURE", PASS, detail))

    # G5 literal / relocation overlap.
    relocs = ctx.relocs_in(toff, toff + window)
    v.gates.append(Gate("RELOCATION_OVERLAP", FAIL if relocs else PASS,
                        f"{len(relocs)} sites in window"))
    # Absolute 8-byte literals pointing into the window interior.
    literal_hits = ctx.literals_in(toff, toff + window)
    v.gates.append(Gate("LITERAL_OVERLAP", FAIL if literal_hits else PASS,
                        f"{len(literal_hits)} absolute literals into window"))

    # G6 runtime rewrite tables.
    exb = ctx.ex_table_in(toff, toff + window)
    alb = ctx.alts_in(toff, toff + window)
    v.gates.append(Gate("EXTABLE_OVERLAP", FAIL if exb else PASS,
                        f"{len(exb)} insn addresses"))
    v.gates.append(Gate("ALTERNATIVES_OVERLAP", FAIL if alb else PASS,
                        f"{len(alb)} overlapping alt ranges"))
    v.gates.append(Gate("OTHER_REWRITE_SECTIONS", PASS if all(
        name in ctx.absent_rewrite_sections for name in
        ("__jump_table", ".static_call_sites", ".kcfi_traps")) else PENDING,
        ", ".join(ctx.absent_rewrite_sections) + " ABSENT (frozen audit.json)"))

    # G7 initcall-table overlap 0 + PREL32 unchanged.
    if ctx.late_table:
        table_hits = [e.index for e in ctx.late_table
                      if e.entry_image_offset < toff + window
                      and e.entry_image_offset + 4 > toff]
        interior_targets = [e.index for e in ctx.late_table
                            if toff < e.target_va - TEXT_VA < toff + window]
        own = (cand.index if toff <= cand.entry_image_offset < toff + window
               else None)
        if table_hits or interior_targets or own is not None:
            v.gates.append(Gate("INITCALL_TABLE_OVERLAP", FAIL,
                                f"table words {table_hits} interior targets "
                                f"{interior_targets} own={own}"))
        else:
            v.gates.append(Gate("INITCALL_TABLE_OVERLAP", PASS,
                                "0 of 86 entry words in window, 0 interior targets"))
        v.gates.append(Gate("PREL32_UNCHANGED", PASS,
                            "patch confined to code window; entry words untouched"))
    else:
        v.gates.append(Gate("INITCALL_TABLE_OVERLAP", PENDING,
                            "late-table not loaded"))
        v.gates.append(Gate("PREL32_UNCHANGED", PENDING, "late-table not loaded"))

    # G8 registration macro (only locally decidable with a pinned tree; the
    # authoritative CI source-contract gate owns it otherwise).
    if ctx.source_tree is not None:
        try:
            reg = find_registration(ctx.source_tree, cand.aliases)
            v.gates.append(Gate("REGISTRATION", PASS if reg else FAIL, reg or ""))
        except AuditError as exc:
            v.gates.append(Gate("REGISTRATION", FAIL, str(exc)))
    return v


def find_registration(linux: Path, aliases) -> str:
    """Unique late_initcall / late_initcall_sync registration for an alias."""
    import re
    names = tuple(aliases)
    pattern = re.compile(
        r"\b(late_initcall(?:_sync)?)\s*\(\s*(" + "|".join(names) + r")\s*\)")
    hits = []
    for path in linux.rglob("*.c"):
        text = path.read_text(errors="replace")
        for m in pattern.finditer(text):
            hits.append(f"{m.group(1)}({m.group(2)}) {path.relative_to(linux)}")
    require(len(hits) >= 1, f"INITCALL_SPAN_UNREGISTERED:{aliases}")
    require(len({h.split()[0] for h in hits}) == 1,
            f"INITCALL_SPAN_MACRO_AMBIGUOUS:{hits}")
    return "; ".join(hits)


# ---------------------------------------------------------------------------
# Nearest-safe-neighbor selection from the nominal upper-child index
# ---------------------------------------------------------------------------

def neighbor_order(count: int, nominal: int):
    return sorted(range(count),
                  key=lambda i: (abs(i - nominal), 0 if i < nominal else 1))


def select_upper_child(ctx: AuthoritativeMap, nominal=NOMINAL_UPPER_CHILD_INDEX,
                       branch_index=None, limit=None):
    """Evaluate neighbors from the nominal index outward; return
    (first_passable_verdict, all_verdicts, order)."""
    require(ctx.late_table, "LATE_TABLE_NOT_LOADED")
    order = neighbor_order(len(ctx.late_table), nominal)
    if limit:
        order = order[:limit]
    verdicts, first_pass = [], None
    for i in order:
        cand = ctx.late_table[i]
        verdict = evaluate(ctx, cand, branch_index=branch_index)
        verdicts.append(verdict)
        if first_pass is None and verdict.geometry_passed:
            first_pass = verdict
            break
    return first_pass, verdicts, order


# ---------------------------------------------------------------------------
# Level-7 completion boundary bracket
# ---------------------------------------------------------------------------

LEVEL7_COMPLETION_CHECKPOINT = {
    "statement": "LEVEL7_COMPLETION_CHECKPOINT=CANDIDATE(late_complete)",
    "candidate_window_image": [hex(LATE_COMPLETE_WINDOW[0]), hex(LATE_COMPLETE_WINDOW[1])],
    "candidate_size": LATE_COMPLETE_WINDOW[1] - LATE_COMPLETE_WINDOW[0],
    "predecessor": "do_basic_setup",
    "causal_chain": [
        "do_initcall_level(7) iterates the 86-entry late span "
        "[__initcall7_start=0xffff800081d0c2d8, __initcall_end=0xffff800081d0c430) "
        "with no early exit; returning implies every late entry returned",
        "do_initcalls() loops level=0..7 sequentially; its return implies "
        "do_initcall_level(7) returned",
        "do_basic_setup() ends with do_initcalls() (byte-exact tail verified in "
        "artifacts/slot-b-post-initcalls-20260919/ci/l7-late-complete/audit/"
        "basic-setup.txt); its return implies do_initcalls() returned",
        "kernel_init_freeable executes bl wait_for_initramfs at image 0x1b3113c "
        "immediately after the bl do_basic_setup at 0x1b31138; the late_complete "
        "window [0x1b3113c, 0x1b31174) replaces that call, so the probe fires "
        "iff do_basic_setup returned",
    ],
    "probe_architecture": "INLINE_CALLSITE_NO_ADDED_LANDING_PAD",
    "pair_diff": [hex(CALLER_PAIR_DIFF[0]), hex(CALLER_PAIR_DIFF[1])],
    "expected_delta_s": EXPECTED_PAIR_DELTA_S,
    "acceptance_rule": (
        "LATE_INITCALLS_COMPLETED upgrades to PROVEN iff a device pair at "
        "late_complete (or at a strictly later checkpoint that causally implies "
        "late_complete execution) is STRONG: "
        "|PAIR_DELTA - (-7.0)| <= 1.0s"
    ),
    "positive_proves": "late_initcalls_completed",
    "positive_does_not_prove": "wait_for_initramfs_return",
    "negative_rules": [
        "A STRONG pair at any interior late entry (indices 0..85, including "
        "index 85) does NOT imply completion: it proves only that the entries "
        "before that index were reached/executed; the remaining entries and "
        "the level return stay unproven.",
        "The WAITENTRY8/1 device pair observed SHIFT_NOT_OBSERVED "
        "(+3.200119584s vs expected -7.000s). A no-shift is an absence of "
        "evidence: it implies neither completion nor non-completion and must "
        "never be upgraded to LATE_INITCALLS_COMPLETED=PROVEN or to any "
        "'not executed / not completed' claim. WAITENTRY8/1 are rerun-FORBIDDEN.",
        "A last-late-entry (index 85) STRONG does NOT license "
        "LATE_INITCALLS_COMPLETED=PROVEN; only a checkpoint causally AFTER the "
        "entire level-7 return can.",
    ],
    "dominating_checkpoints": [
        {"name": "late_complete", "window": [hex(LATE_COMPLETE_WINDOW[0]),
                                             hex(LATE_COMPLETE_WINDOW[1])],
         "size": 56, "implies": "do_basic_setup returned"},
        {"name": "wait_complete", "window": [hex(WAIT_COMPLETE_WINDOW[0]),
                                             hex(WAIT_COMPLETE_WINDOW[1])],
         "size": 52,
         "implies": "wait_for_initramfs returned, hence the preceding "
                    "bl wait_for_initramfs executed, hence do_basic_setup "
                    "returned (strictly later than late_complete)"},
    ],
}


def verify_boundary_bracket(audit_json: dict, window_txt: str) -> dict:
    """Machine-check the frozen post-initcalls evidence against the encoded
    bracket. Returns the verified statement dict."""
    require(audit_json["symbol"] == "late_complete", "BRACKET_SYMBOL_DRIFT")
    require(int(audit_json["target_va"], 16) == TEXT_VA + LATE_COMPLETE_WINDOW[0],
            "BRACKET_WINDOW_DRIFT")
    require(audit_json["checkpoint_size"] == 56, "BRACKET_SIZE_DRIFT")
    require(audit_json["offset"] == LATE_COMPLETE_WINDOW[0], "BRACKET_OFFSET_DRIFT")
    require(audit_json["probe_architecture"] == "INLINE_CALLSITE_NO_ADDED_LANDING_PAD",
            "BRACKET_ARCHITECTURE_DRIFT")
    require(audit_json["predecessor"] == "do_basic_setup", "BRACKET_PREDECESSOR_DRIFT")
    require(audit_json["positive_proves"] == "late_initcalls_completed",
            "BRACKET_PROOF_DRIFT")
    require(audit_json["late_entry_count"] == LATE_SPAN_COUNT, "BRACKET_SPAN_DRIFT")
    want = f"{TEXT_VA + LATE_COMPLETE_WINDOW[0]:x}"
    require(any(line.strip().startswith(want) for line in window_txt.splitlines()),
            "BRACKET_WINDOW_TXT_DRIFT")
    # Device-round convention: PAIR_DELTA = TOTAL(1) - TOTAL(8); a working
    # 8s/1s delay pair is expected at -7.000s.
    require(WAITENTRY_PAIR_DELTA_S == round(
        WAITENTRY_TOTALS["1"] - WAITENTRY_TOTALS["8"], 9), "WAITENTRY_DELTA_DRIFT")
    require(WAITENTRY_PAIR_DELTA_S > 0, "WAITENTRY_SHIFT_SIGN_DRIFT")
    verdict = {
        "verified": True,
        "strong": abs(WAITENTRY_PAIR_DELTA_S - EXPECTED_PAIR_DELTA_S)
        <= STRONG_TOLERANCE_S,
        "observed_delta_s": WAITENTRY_PAIR_DELTA_S,
        "expected_delta_s": EXPECTED_PAIR_DELTA_S,
        "verdict_label": "SHIFT_NOT_OBSERVED",
        "completion_claim": "NONE (no-shift licenses neither completion nor "
                            "non-completion)",
    }
    return verdict


def completion_claim(checkpoint: str, delta_s: float) -> dict:
    """Apply the acceptance rule to a hypothetical pair result."""
    strong = abs(delta_s - EXPECTED_PAIR_DELTA_S) <= STRONG_TOLERANCE_S
    dominating = {c["name"] for c in LEVEL7_COMPLETION_CHECKPOINT["dominating_checkpoints"]}
    if checkpoint not in dominating:
        return {"checkpoint": checkpoint, "strong": strong,
                "claim": "INVALID_CHECKPOINT",
                "reason": "interior late entries (0..85, incl. 85) never imply "
                          "LATE_INITCALLS_COMPLETED"}
    return {"checkpoint": checkpoint, "strong": strong,
            "claim": "LATE_INITCALLS_COMPLETED=PROVEN" if strong
            else "NO_UPGRADE (pair not STRONG; no completion claim either way)"}


# ---------------------------------------------------------------------------
# Artifact loading (pure python, GHA-produced material only)
# ---------------------------------------------------------------------------

def load_late_table(path: Path) -> tuple:
    raw = json.loads(path.read_text())
    require(len(raw) == LATE_SPAN_COUNT, "LATE_TABLE_COUNT_DRIFT")
    cands = tuple(Candidate(
        index=e["index"], symbol=e["symbol"], target_va=e["target_va"],
        entry_va=e["entry_va"], entry_image_offset=e["entry_image_offset"],
        entry_word=int(e["entry_word"], 16), relative=e["relative"],
        aliases=tuple(e["aliases"])) for e in raw)
    require(cands[0].entry_va == INITCALL7_START_VA, "LATE_SPAN_START_DRIFT")
    require(cands[-1].entry_va + 4 == INITCALL_END_VA, "LATE_SPAN_END_DRIFT")
    return cands


def parse_elf(path: Path):
    """Minimal ELF64 LE reader: sections + symbols (+ raw bytes on demand).
    The caller owns the returned file handle (closed via close_elf)."""
    f = open(path, "rb")
    try:
        head = f.read(64)
    except Exception:
        f.close()
        raise
    require(head[:4] == b"\x7fELF" and head[4] == 2 and head[5] == 1,
            "NOT_ELF64_LE")
    e_shoff, = struct.unpack_from("<Q", head, 0x28)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", head, 0x3A)
    f.seek(e_shoff)
    raw = f.read(e_shentsize * e_shnum)
    secs = []
    for i in range(e_shnum):
        base = i * e_shentsize
        name, typ, flags, addr, off, size = struct.unpack_from("<IIQQQQ", raw, base)
        link, info, align, entsz = struct.unpack_from("<IIQQ", raw, base + 40)
        secs.append(dict(idx=i, sh_name=name, type=typ, flags=flags, vma=addr,
                         off=off, size=size, link=link, entsz=entsz))
    shstr = secs[e_shstrndx]
    f.seek(shstr["off"]); shstrtab = f.read(shstr["size"])
    for s in secs:
        end = shstrtab.index(b"\x00", s["sh_name"])
        s["name"] = shstrtab[s["sh_name"]:end].decode()
    return f, secs


def close_elf(f):
    f.close()


def read_section(f, sec) -> bytes:
    f.seek(sec["off"])
    return f.read(sec["size"])


def build_context(image_path: Path, image_sha_expected: str | None,
                  vmlinux_path: Path | None = None, late_table_path: Path = None,
                  source_tree: Path | None = None,
                  patched_windows=()) -> AuthoritativeMap:
    image = image_path.read_bytes()
    ctx = AuthoritativeMap(
        image=image, image_evidence=str(image_path),
        image_sha_expected=image_sha_expected, exec_ranges=(), symbol_vas=(),
        symbol_st_size={}, reloc_sites=(), ex_table_insns=(), alt_ranges=(),
        patched_windows=tuple(patched_windows), late_table=(),
        source_tree=source_tree)
    if vmlinux_path is not None:
        f, secs = parse_elf(vmlinux_path)
        try:
            byname = {s["name"]: s for s in secs}
            ctx.exec_ranges = tuple(
                (s["vma"] - TEXT_VA, s["vma"] - TEXT_VA + s["size"])
                for s in secs if s["flags"] & 0x7 == 0x6 and s["size"])  # A|X
            strtab, symtab = byname[".strtab"], byname[".symtab"]
            strdata = read_section(f, strtab)
            symdata = read_section(f, symtab)
            vas, st_size = set(), {}
            for i in range(0, len(symdata), 24):
                nameoff, info, _other, _shn, value, size = struct.unpack_from(
                    "<IBBHQQ", symdata, i)
                if not nameoff:
                    continue
                vas.add(value)
                if info & 0xF == 2 and size:
                    st_size[value] = size
            ctx.symbol_vas = tuple(sorted(vas))
            ctx.symbol_st_size = st_size
            sites = []
            if ".rela.dyn" in byname:
                rdata = read_section(f, byname[".rela.dyn"])
                for i in range(0, len(rdata), 24):
                    r_offset, r_info, _addend = struct.unpack_from("<QQq", rdata, i)
                    if r_info & 0xFFFFFFFF == 1027:  # R_AARCH64_RELATIVE
                        sites.append(r_offset - TEXT_VA)
            if ".relr.dyn" in byname:
                rldata = read_section(f, byname[".relr.dyn"])
                where = None
                for (entry,) in struct.iter_unpack("<Q", rldata):
                    if not entry & 1:
                        sites.append(entry - TEXT_VA); where = entry + 8
                    else:
                        sites.extend(where - TEXT_VA + b * 8 for b in range(63)
                                     if entry & (1 << (b + 1)))
                        where += 63 * 8
            ctx.reloc_sites = tuple(sorted(set(sites)))
            def _s32(data, off):
                return struct.unpack_from("<i", data, off)[0]
            if "__ex_table" in byname:
                sec = byname["__ex_table"]
                data = read_section(f, sec)
                ctx.ex_table_insns = tuple(sorted(
                    sec["vma"] + i + _s32(data, i) - TEXT_VA
                    for i in range(0, len(data) - 11, 12)))
            if ".altinstructions" in byname:
                sec = byname[".altinstructions"]
                data = read_section(f, sec)
                ctx.alt_ranges = tuple(sorted(
                    (sec["vma"] + i + _s32(data, i) - TEXT_VA,
                     sec["vma"] + i + _s32(data, i) + data[i + 11] - TEXT_VA)
                    for i in range(0, len(data) - 11, 12)))
            absent = tuple(n for n in ("__jump_table", ".static_call_sites",
                                       ".kcfi_traps") if n not in byname)
            ctx.absent_rewrite_sections = absent
        finally:
            close_elf(f)
    if late_table_path is not None:
        ctx.late_table = load_late_table(late_table_path)
    return ctx


# ---------------------------------------------------------------------------
# CLI pre-audit for the HIGH candidate
# ---------------------------------------------------------------------------

def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path,
                        default=root / "artifacts/slot-b-post-initcalls-20260919")
    parser.add_argument("--bundle", type=Path,
                        default=root / "artifacts/slot-b-level6-inline-20260918/bundle")
    parser.add_argument("--payload", type=Path,
                        default=root / "artifacts/slot-b-level7-20260918/"
                                       "pair/8/checkpoint/payload.bin")
    parser.add_argument("--source-tree", type=Path, default=root / "linux-6.6")
    parser.add_argument("--limit", type=int, default=6,
                        help="neighbor scan depth from the nominal index")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    source_tree = (args.source_tree
                   if (args.source_tree / "init" / "main.c").exists() else None)

    audit_dir = args.artifacts / "ci/l7-late-complete/audit"
    late_table = audit_dir / "late-table.json"
    audit_json = json.loads((audit_dir / "audit.json").read_text())
    window_txt = (audit_dir / "window.txt").read_text()

    # The level-7 DEVPROBE8 payload carries the frozen kernel bytes everywhere
    # outside its own probe window; sha-pinned to the GHA-recorded value.
    payload_sha = digest(args.payload.read_bytes())
    require(payload_sha == LEVEL7_DEVPROBE8_PAYLOAD_SHA, "PAYLOAD_SHA_DRIFT")
    ctx = build_context(
        image_path=args.payload, image_sha_expected=LEVEL7_DEVPROBE8_PAYLOAD_SHA,
        vmlinux_path=args.bundle / "vmlinux", late_table_path=late_table,
        source_tree=source_tree,
        patched_windows=((0x1B32078, 0x1B32078 + 60),))
    require(digest((args.bundle / "vmlinux").read_bytes()) == FROZEN_BUNDLE_ELF_SHA,
            "BUNDLE_ELF_SHA_DRIFT")
    bracket = verify_boundary_bracket(audit_json, window_txt)

    branch_index = ctx.branch_index()
    first, verdicts, order = select_upper_child(ctx, branch_index=branch_index,
                                                limit=args.limit)
    report = {
        "round": "MAINLINE_V2_R3_SLOT_B_LATE_LEVEL_FAILURE_ISOLATION",
        "auditor": "Sub Agent C (independent CFG/geometry cross-check)",
        "nominal_upper_child": NOMINAL_UPPER_CHILD_INDEX,
        "late_span": {"start": hex(INITCALL7_START_VA), "end": hex(INITCALL_END_VA),
                      "entries": LATE_SPAN_COUNT},
        "boundary_bracket": {**LEVEL7_COMPLETION_CHECKPOINT,
                             "device_pair_verification": bracket},
        "neighbor_order_from_nominal": order[:args.limit],
        "evaluations": [v.as_dict() for v in verdicts],
        "first_passable": first.as_dict() if first else None,
        "pending": ["authoritative GHA nm/objdump re-derivation of every "
                    "LOCAL_BINARY fact before any device round"],
    }
    text = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
