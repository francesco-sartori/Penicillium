"""Figures and tables of docs/validation_octave.md from the Octave batches in validation/octave/data.

Usage:
    python validation/octave/report.py [--collect RUNS_DIR]

``--collect`` first copies the ``case_NN.mat`` files written by run_indpensim_v201.m (default tolerances in
RUNS_DIR/default, RelTol 1e-8 in RUNS_DIR/tight, any depth) into validation/octave/data, compressed.
Writes docs/img/octave_*.png and validation/octave/results.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
from scipy.io import loadmat, savemat

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from compare_octave import DATA, compare, errors, load, replay

ROOT = Path(__file__).resolve().parents[2]
IMG = ROOT / "docs" / "img"
OCTAVE, PENICILLIUM = "#e6550d", "#08519c"  # same pair as the 100-batch figure
TIGHT = {"rtol": 1e-10, "atol": 1e-12}  # Penicillium settings for the tight comparison
FAULTS = [
    "none",
    "aeration",
    "pressure",
    "substrate feed",
    "base flow",
    "coolant flow",
    "all of 1-5",
    "temperature sensor",
    "pH sensor",
]
RAMAN = {1: "Raman", 2: "PAT"}  # Raman_spec 1: spectra recorded; 2: spectra and PAT control of PAA


def collect(runs: Path) -> None:
    for sub in ("default", "tight"):
        dst = DATA / sub if sub == "tight" else DATA
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted((runs / sub).rglob("case_*.mat")):
            m = {k: v for k, v in loadmat(f).items() if not k.startswith("__")}
            savemat(dst / f.name, m, do_compression=True)
            print("collected", dst / f.name)


def describe(case: dict) -> str:
    cf = case["flags"]
    parts = ["PRBS" if cf.PRBS else "recipe", f"{case['T']:g} h"]
    if cf.Faults:
        parts.append(f"fault {int(cf.Faults)}")
    if cf.Raman_spec:
        parts.append(RAMAN[int(cf.Raman_spec)])
    return ", ".join(parts)


def short(case: dict) -> str:
    """What sets the batch apart from the 230 h recipe batch, for axis labels."""
    cf = case["flags"]
    parts = (["PRBS"] if cf.PRBS else []) + ([f"{case['T']:g} h"] if case["T"] != 230 else [])
    parts += ([f"fault {int(cf.Faults)}"] if cf.Faults else []) + ([RAMAN[int(cf.Raman_spec)]] if cf.Raman_spec else [])
    return "\n".join(parts) or "recipe"


def fig_agreement(rows: list[dict], cases: list[dict]) -> None:
    x = np.arange(1, len(rows) + 1)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.axhline(1e-3, color="0.5", lw=1, ls="--")
    ax.text(len(rows) + 0.4, 1e-3, "criterion 1e-3", va="bottom", ha="right", fontsize=8, color="0.35")
    ax.plot(x, [r["yield_rel_err"] for r in rows], "o", ms=7, color=PENICILLIUM, label="total yield")
    ax.plot(
        x,
        [r["states_mean"] for r in rows],
        "s",
        ms=6,
        mfc="white",
        mec=PENICILLIUM,
        mew=1.5,
        label="process states, mean over the batch",
    )
    ax.set_yscale("log")
    ax.set_xticks(x, [f"{i}\n{short(c)}" for i, c in zip(x, cases, strict=True)], fontsize=8)
    ax.set_ylabel("relative difference")
    ax.set_title("Penicillium vs IndPenSim V2.01 (Octave), default solver settings", fontsize=10, loc="left")
    ax.grid(axis="y", color="0.9")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "octave_agreement.png", dpi=110)
    plt.close(fig)


def fig_batch(path: Path, channels: list[tuple[str, str]], out: str, title: str) -> None:
    case = load(path)
    res = replay(path)
    t = np.arange(1, len(case["ref"]["S"]) + 1) * 0.2
    fig, axes = plt.subplots(2, 3, figsize=(11, 5), sharex=True)
    for ax, (ch, label) in zip(axes.flat, channels, strict=True):
        ax.plot(t, case["ref"][ch], color=OCTAVE, lw=2.4, label="V2.01 (Octave)")
        ax.plot(t, np.asarray(res[ch])[: len(t)], color=PENICILLIUM, lw=1, label="Penicillium")
        ax.set_title(f"{label}   max diff {errors(res, case['ref'], ch).max():.0e}", fontsize=9, loc="left")
        ax.grid(color="0.92")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    for ax in axes[1]:
        ax.set_xlabel("time [h]")
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle(title, fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(IMG / out, dpi=110)
    plt.close(fig)


def fig_episode(default: Path, tight: Path) -> None:
    """Batch 3 around the CO2 threshold, at V2.01's default tolerance and at tight tolerances."""
    fig, axes = plt.subplots(2, 3, figsize=(11, 5.2), sharex=True)
    for row, (path, kw, label) in enumerate(
        (
            (default, {}, "default tolerances (Octave RelTol 1e-3, Penicillium 1e-5)"),
            (tight, TIGHT, "tight tolerances (Octave RelTol 1e-8, Penicillium 1e-10)"),
        )
    ):
        case = load(path)
        res = replay(path, **kw)
        t = np.arange(1, len(case["ref"]["S"]) + 1) * 0.2
        w = (t >= 84) & (t <= 96)
        for ax, (ch, name) in zip(
            axes[row], (("CO2_d", "dissolved CO2"), ("mu_X_calc", "biomass growth rate"), ("pH", "pH")), strict=True
        ):
            ax.plot(t[w], case["ref"][ch][w], color=OCTAVE, lw=2.4, label="V2.01 (Octave)")
            ax.plot(t[w], np.asarray(res[ch])[: len(t)][w], color=PENICILLIUM, lw=1, label="Penicillium")
            if ch == "CO2_d":
                ax.axhline(7.57, color="0.4", lw=1, ls="--")
                ax.text(84.2, 7.53, "inhibition threshold 7.57", fontsize=7, color="0.3", va="top")
            ax.set_title(name, fontsize=9, loc="left")
            ax.grid(color="0.92")
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        axes[row, 0].set_ylabel(label.split(" (")[0], fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("time [h]")
    axes[0, 0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("Batch 3: dissolved CO2 reaches the inhibition threshold at 88 h", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(IMG / "octave_batch03_episode.png", dpi=110)
    plt.close(fig)


def fig_tolerance(pairs: list[tuple[int, dict, dict, dict]]) -> None:
    """Mean state difference per batch: both at default tolerances, Penicillium default vs tight Octave, both tight."""
    labels = [f"batch {i}" for i, *_ in pairs]
    series = [
        ("both at default tolerances", 1, "#c6dbef"),
        ("Penicillium default vs Octave tight", 2, "#6baed6"),
        ("both tight", 3, PENICILLIUM),
    ]  # loose to tight, light to dark (orange means Octave elsewhere)
    x = np.arange(len(pairs))
    fig, ax = plt.subplots(figsize=(8, 3.4))
    for j, (name, idx, color) in enumerate(series):
        ax.bar(
            x + (j - 1) * 0.26,
            [p[idx]["states_mean"] for p in pairs],
            0.24,
            color=color,
            label=name,
            edgecolor="white",
            linewidth=1,
        )
    ax.set_yscale("log")
    ax.set_xticks(x, labels)
    ax.set_ylabel("state difference, mean over\nthe batch (relative to peak)")
    ax.grid(axis="y", color="0.9")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "octave_tolerance.png", dpi=110)
    plt.close(fig)


def tables(rows: list[dict], cases: list[dict], tight_rows: list[tuple[int, dict, dict, dict]]) -> str:
    out = [
        "## Batches",
        "",
        "| Batch | Batch_no | Random_seed_ref | Control | Length | T [h] | Fault | Raman_spec |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(cases, 1):
        cf = c["flags"]
        out.append(
            f"| {i} | {int(cf.Batch_Num)} | {int(c['mat']['Random_seed_ref'])} | "
            f"{'operator (PRBS)' if cf.PRBS else 'recipe'} | {'variable' if cf.Fixed_Batch_length else 'fixed'} | "
            f"{c['T']:g} | {int(cf.Faults)} ({FAULTS[int(cf.Faults)]}) | {int(cf.Raman_spec)} |"
        )
    cols = [
        ("S", "S [g/L]", 4),
        ("DO2", "DO2 [mg/L]", 3),
        ("X", "X [g/L]", 4),
        ("V", "V [L]", 0),
        ("Wt", "Wt [kg]", 0),
        ("pH", "pH", 3),
        ("T", "T [K]", 2),
        ("PAA", "PAA [mg/L]", 1),
        ("NH3", "NH3 [mg/L]", 1),
        ("O2", "O2 [-]", 4),
        ("CO2outgas", "CO2 [%]", 4),
        ("mux", "mu_x [1/h]", 4),
        ("mup", "mu_p [1/h]", 5),
    ]
    extra = [("alpha_kla", "alpha_kla", 2), ("PAA_c", "PAA_c [mg/L]", 0), ("N_conc_paa", "N_conc_paa [mg/L]", 0)]
    out += [
        "",
        "## Initial conditions and batch parameters",
        "",
        "| Batch | " + " | ".join(h for _, h, _ in cols + extra) + " |",
        "|---" * (len(cols) + len(extra) + 1) + "|",
    ]
    for i, c in enumerate(cases, 1):
        m = c["mat"]
        vals = [f"{float(getattr(m['x0'], k)):.{d}f}" for k, _, d in cols]
        vals += [f"{float(m[k]):.{d}f}" for k, _, d in extra]
        out.append(f"| {i} | " + " | ".join(vals) + " |")
    out += [
        "",
        "## Results at default solver settings",
        "",
        "| Batch | Type | Yield V2.01 [kg] | Yield Penicillium [kg] | Yield diff | States, mean diff | "
        "States, worst diff | Samples with a state diff > 1e-3 | Penicillium [s] | Octave [s] |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, (r, c) in enumerate(zip(rows, cases, strict=True), 1):
        out.append(
            f"| {i} | {describe(c)} | {r['yield_octave_kg']:.1f} | {r['yield_penicillium_kg']:.1f} | "
            f"{r['yield_rel_err']:.1e} | {r['states_mean']:.1e} | {r['states_max']:.1e} | "
            f"{r['samples_over_1e-3']} of {r['samples']} | {r['penicillium_s']:.1f} | {r['octave_s']:.0f} |"
        )
    out += [
        "",
        "## Tight tolerances",
        "",
        "| Batch | Yield diff: both default | Penicillium default vs Octave tight | both tight | "
        "States, mean diff: both default | Penicillium default vs Octave tight | both tight | "
        "Samples with a state diff > 1e-3: both default | both tight |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, d, pd_, t in tight_rows:
        out.append(
            f"| {i} | {d['yield_rel_err']:.1e} | {pd_['yield_rel_err']:.1e} | {t['yield_rel_err']:.1e} | "
            f"{d['states_mean']:.1e} | {pd_['states_mean']:.1e} | {t['states_mean']:.1e} | "
            f"{d['samples_over_1e-3']} | {t['samples_over_1e-3']} of {t['samples']} |"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--collect", type=Path, default=None)
    args = ap.parse_args()
    if args.collect:
        collect(args.collect)
    paths = sorted(DATA.glob("case_*.mat"))
    cases = [load(p) for p in paths]
    rows = [compare(p) for p in paths]
    for r in rows:
        print(
            f"{r['case']}: yield {r['yield_rel_err']:.1e}, states mean {r['states_mean']:.1e}, "
            f"max {r['states_max']:.1e}, first > 1e-3 at {r['first_divergence_h']} h"
        )
    tight_rows = []
    for p in sorted((DATA / "tight").glob("case_*.mat")):
        i = int(p.stem.split("_")[1])
        t, pd_ = compare(p, **TIGHT), compare(p)
        tight_rows.append((i, rows[i - 1], pd_, t))
        print(
            f"tight {p.stem}: yield {t['yield_rel_err']:.1e}, states max {t['states_max']:.1e}; "
            f"Penicillium default vs tight Octave {pd_['states_max']:.1e}"
        )
    IMG.mkdir(exist_ok=True)
    fig_agreement(rows, cases)
    fig_batch(
        DATA / "case_01.mat",
        [
            ("P", "penicillin [g/L]"),
            ("X", "biomass [g/L]"),
            ("S", "substrate [g/L]"),
            ("DO2", "dissolved O2 [mg/L]"),
            ("T", "temperature [K]"),
            ("pH", "pH"),
        ],
        "octave_batch01.png",
        "Batch 1 (recipe, 230 h), default solver settings",
    )
    fig_batch(
        DATA / "case_09.mat",
        [
            ("P", "penicillin [g/L]"),
            ("X", "biomass [g/L]"),
            ("Fs", "sugar feed [L/h]"),
            ("DO2", "dissolved O2 [mg/L]"),
            ("T", "temperature [K]"),
            ("Fc", "cooling water [L/h]"),
        ],
        "octave_batch09.png",
        "Batch 9 (all of faults 1-5), default solver settings",
    )
    if (DATA / "tight" / "case_03.mat").exists():
        fig_episode(DATA / "case_03.mat", DATA / "tight" / "case_03.mat")
    if tight_rows:
        fig_tolerance(tight_rows)
    (Path(__file__).parent / "results.md").write_text(
        "<!-- generated by validation/octave/report.py -->\n\n" + tables(rows, cases, tight_rows), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
