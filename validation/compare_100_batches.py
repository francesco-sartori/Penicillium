"""Statistical validation against the published 100-batch IndPenSim data set (Goldrick, 2019).

MATLAB's random streams cannot be reproduced, so batch ``n`` here is not batch ``n`` of the data set. Instead this
script simulates campaigns with the data set's structure -- for every published batch the same control strategy,
batch length and fault -- and compares distributions:

* yields and final penicillin per strategy (means, standard deviations, two-sample Kolmogorov-Smirnov tests);
* trajectory envelopes per strategy: how often the published batches fall inside the simulated 5-95 % band at each
  time, and how far the medians are apart.

The fault type of each faulty batch (91-100) is not labelled in the data; it is read from the input signatures of
IndPenSim's fault profiles (e.g. aeration at 20 L/h on samples 100-120).

    python validation/compare_100_batches.py --replicates 3 --jobs 8

Writes ``docs/validation_100_batches.md`` and ``docs/img/validation_100_batches.png``.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from indpensim_100_batches import DOI, load_process, load_statistics

from penicillium import BatchSpec, Fault, RamanMode, SimulationConfig, __version__, simulate_batches
from penicillium.simulator import _FAULT_PROFILES

ROOT = Path(__file__).parents[1]
STRATEGIES = {"recipe": range(1, 31), "operator": range(31, 61), "apc": range(61, 91), "fault": range(91, 101)}
CHANNELS = ["P", "V", "S", "DO2", "T", "pH", "CO2outgas", "OUR", "Fs", "Fpaa", "Fb", "Fc"]
LABELS = {
    "P": "penicillin [g/L]", "V": "volume [L]", "S": "substrate [g/L]", "DO2": "dissolved O2 [mg/L]",
    "T": "temperature [K]", "pH": "pH", "CO2outgas": "CO2 off-gas [%]", "OUR": "OUR [g/min]",
    "Fs": "sugar feed [L/h]", "Fpaa": "PAA feed [L/h]", "Fb": "base flow [L/h]", "Fc": "cooling water [L/h]",
}  # fmt: skip
# Every channel recorded both in the published data set and by Penicillium, for the coverage appendix. The recipe
# inputs are listed too, although they follow the same recipe in both.
APPENDIX_CHANNELS = {
    "process states and measurements": ["S", "DO2", "O2", "P", "V", "Wt", "pH", "T", "Q", "CO2outgas", "OUR", "CER"],
    "controller outputs": ["Fa", "Fb", "Fc", "Fh"],
    "recipe inputs (PRBS, PAT control or a fault where they apply)": ["Fs", "Fpaa", "Foil", "Fg", "pressure", "Fw", "discharge", "RPM"],
}  # fmt: skip


def strategy_of(batch_id: int) -> str:
    return next(name for name, ids in STRATEGIES.items() if batch_id in ids)


def infer_fault(d: pd.DataFrame) -> Fault:
    """IndPenSim fault type of a published batch, from the signature of its fault profile in the inputs."""
    k = np.arange(1, len(d) + 1)

    def holds(col, value, lo, hi):
        m = (k >= lo) & (k <= min(hi, len(d)))
        return m.any() and np.allclose(d[col].to_numpy()[m], value)

    if d["Fault_ref"].max() == 0:
        return Fault.NONE
    checks = [
        (Fault.AERATION, holds("Fg", 20, 100, 120)),
        (Fault.PRESSURE, holds("pressure", 2, 500, 520)),
        (Fault.SUBSTRATE_FEED, holds("Fs", 2, 100, 150)),
        (Fault.BASE_FLOW, holds("Fb", 5, 400, 420)),
        (Fault.COOLANT_FLOW, holds("Fc", 2, 350, 450)),
    ]
    found = [f for f, ok in checks if ok]
    if len(found) > 1:
        return Fault.ALL
    if found:
        return found[0]
    # Sensor drifts leave no input signature; the controller holds the measured value at the setpoint.
    late = k > 800
    return Fault.TEMPERATURE_SENSOR if d["T"][late].mean() < 297.8 else Fault.PH_SENSOR


def published_batches(df: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    yields = dict(zip(stats_df.iloc[:, 0].astype(int), stats_df.iloc[:, 3] / 1000, strict=True))
    for b, d in df.groupby("batch_id"):
        rows.append({
            "batch_id": int(b), "strategy": strategy_of(int(b)), "length_h": float(d["time_h"].max()),
            "fault": infer_fault(d.reset_index(drop=True)), "yield_kg": float(yields[int(b)]),
            "final_P": float(d["P"].iloc[-1]),
        })  # fmt: skip
    return pd.DataFrame(rows)


def simulate(plan: pd.DataFrame, replicates: int, jobs: int | None) -> tuple[pd.DataFrame, list]:
    specs, meta = [], []
    for r in range(replicates):
        for row in plan.itertuples():
            cfg = SimulationConfig(
                fault=Fault(row.fault),
                prbs=row.strategy == "operator",
                raman_mode=RamanMode.PAT_CONTROL if row.strategy == "apc" else RamanMode.OFF,
                batch_length_h=row.length_h,
            )
            specs.append(BatchSpec(seed=7_000_000 + 1000 * r + row.batch_id, config=cfg))
            meta.append({"replicate": r, "batch_id": row.batch_id, "strategy": row.strategy, "fault": row.fault})
    results = simulate_batches(specs, n_jobs=jobs, keep_raman=False)
    summary = pd.DataFrame(meta)
    summary["yield_kg"] = [res.total_yield for res in results]
    summary["final_P"] = [float(res["P"][-1]) for res in results]
    return summary, results


def _common_length(df: pd.DataFrame, pub_ids, sim_results) -> int:
    """Samples covered by every published and simulated batch of a strategy."""
    pub = df[df.batch_id.isin(pub_ids)].groupby("batch_id").size().min()
    return int(min(pub, min(len(r) for r in sim_results)))


def envelope_table(df: pd.DataFrame, sim_summary: pd.DataFrame, results: list, channels=CHANNELS) -> pd.DataFrame:
    """Coverage of published trajectories by the simulated 5-95 % band, per strategy and channel."""
    rows = []
    for strategy in STRATEGIES:
        sim_idx = [i for i, s in enumerate(sim_summary["strategy"]) if s == strategy]
        pub_ids = list(STRATEGIES[strategy])
        n = _common_length(df, pub_ids, [results[i] for i in sim_idx])
        for ch in channels:
            sim = np.array([results[i][ch][:n] for i in sim_idx])
            pub = np.array([df.loc[df.batch_id == b, ch].to_numpy()[:n] for b in pub_ids])
            lo, hi = np.percentile(sim, 5, axis=0), np.percentile(sim, 95, axis=0)
            inside = (pub >= lo) & (pub <= hi)
            med_sim, med_pub = np.median(sim, axis=0), np.median(pub, axis=0)
            scale = max(np.percentile(np.abs(pub), 99), 1e-12)
            rows.append({
                "strategy": strategy, "channel": ch, "coverage": float(inside.mean()), "inside": int(inside.sum()),
                "compared": int(inside.size), "median_gap": float(np.mean(np.abs(med_sim - med_pub)) / scale),
            })  # fmt: skip
    return pd.DataFrame(rows)


def welch_interval(pub: pd.Series, sim: pd.Series) -> tuple[float, float, float]:
    """Mean difference (simulated - published) and its 95 % Welch interval."""
    v1, v2 = pub.var(ddof=1) / len(pub), sim.var(ddof=1) / len(sim)
    dof = (v1 + v2) ** 2 / (v1**2 / (len(pub) - 1) + v2**2 / (len(sim) - 1))
    diff, half = sim.mean() - pub.mean(), stats.t.ppf(0.975, dof) * np.sqrt(v1 + v2)
    return float(diff), float(diff - half), float(diff + half)


def ks_power(n_pub: int, n_sim: int, sd: float, shift: float, reps: int = 2000, seed: int = 0) -> float:
    """Share of two-sample KS tests (5 % level) that detect ``shift`` between normal samples of standard deviation ``sd``."""
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((reps, n_pub)) * sd
    b = rng.standard_normal((reps, n_sim)) * sd + shift
    return float(np.mean([stats.ks_2samp(x, y).pvalue < 0.05 for x, y in zip(a, b, strict=True)]))


def detectable_shift(n_pub: int, n_sim: int, sd: float, power: float = 0.8) -> float:
    """Smallest mean shift (searched in steps of 0.05 ``sd``) that the KS test detects with probability ``power``."""
    for k in np.arange(0.05, 3.0, 0.05):
        if ks_power(n_pub, n_sim, sd, k * sd, reps=1000) >= power:
            return float(k * sd)
    return float("nan")


def fault_inference_table(df: pd.DataFrame) -> pd.DataFrame:
    """For each published faulty batch: the fault read from the inputs and the evidence behind it."""
    rows = []
    for b in STRATEGIES["fault"]:
        d = df[df.batch_id == b].reset_index(drop=True)
        k, n = np.arange(1, len(d) + 1), len(d)
        fault = infer_fault(d)
        matches = {}
        for f, profile in _FAULT_PROFILES.items():
            hit = total = 0
            for col, value, lo, hi in profile:
                m = (k >= lo) & (k <= min(hi, n))
                hit += int(np.isclose(d[col].to_numpy()[m], value).sum())
                total += int(m.sum())
            matches[f] = (hit, total)
        others = sum(h for f, (h, _) in matches.items() if f != fault)
        schedule = np.zeros(n, bool)
        for _, _, lo, hi in _FAULT_PROFILES.get(fault, ()):
            schedule |= (k >= lo) & (k <= hi)
        col, value, _, _ = _FAULT_PROFILES[fault][0]
        hit, total = matches[fault]
        rows.append({
            "batch_id": b, "fault": fault, "signal": f"`{col}` = {value}", "matching": f"{hit} of {total}",
            "other_matches": others, "fault_ref_agrees": bool((schedule == (d["Fault_ref"].to_numpy() > 0)).all()),
        })  # fmt: skip
    return pd.DataFrame(rows)


def plot(df: pd.DataFrame, sim_summary: pd.DataFrame, results: list, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chans = ["P", "V", "S", "DO2", "T", "pH", "CO2outgas", "OUR"]
    fig, axes = plt.subplots(len(chans), 3, figsize=(13, 2.2 * len(chans)), sharex=True)
    for col, strategy in enumerate(["recipe", "operator", "apc"]):
        sim_idx = [i for i, s in enumerate(sim_summary["strategy"]) if s == strategy]
        for row, ch in enumerate(chans):
            ax = axes[row, col]
            n = _common_length(df, STRATEGIES[strategy], [results[i] for i in sim_idx])
            t = np.arange(1, n + 1) * 0.2
            sim = np.array([results[i][ch][:n] for i in sim_idx])
            ax.fill_between(t, *np.percentile(sim, [5, 95], axis=0), color="#9ecae1", label="Penicillium 5-95 %")
            ax.plot(t, np.median(sim, axis=0), color="#08519c", lw=1.2, label="Penicillium median")
            for b in STRATEGIES[strategy]:
                ax.plot(t, df.loc[df.batch_id == b, ch].to_numpy()[:n], color="#e6550d", lw=0.4, alpha=0.5)
            if col == 0:
                ax.set_ylabel(LABELS[ch], fontsize=8)
            if row == 0:
                ax.set_title(f"{strategy} (orange: published batches)", fontsize=9)
            ax.tick_params(labelsize=7)
    for ax in axes[-1]:
        ax.set_xlabel("time [h]", fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)


def write_coverage_appendix(env: pd.DataFrame) -> None:
    """``docs/validation_coverage.md``: coverage of every channel and strategy, with the sample counts."""
    states = env[env.channel.isin(next(iter(APPENDIX_CHANNELS.values())))]
    lowest = states.loc[states.coverage.idxmin()]
    by_kind = {
        "faulty": states[states.strategy == "fault"].coverage,
        "other": states[states.strategy != "fault"].coverage,
    }
    lines = [
        "# Appendix: trajectory coverage of every channel",
        "",
        "Generated by `validation/compare_100_batches.py` together with the "
        "[100-batch comparison](validation_100_batches.md).",
        "",
        "For each strategy and channel: the number of published samples that lie inside the simulated 5-95 % band at "
        "the same time, the number of samples compared, and their share (the coverage). Samples are compared up to "
        "the shortest batch of each strategy, published or simulated. When the published and simulated distributions "
        "agree, about 90 % of the published samples are expected inside the band, so about 10 % outside is the "
        "expected result. The samples of one batch are strongly correlated in time and there are 30 published "
        "batches per strategy (10 with faults), so a coverage can differ from 90 % by several percentage points by "
        "chance, more for the faulty batches.",
        "",
        f"**Lowest coverage: {100 * lowest.coverage:.0f} %, for `{lowest.channel}` in the {'faulty' if lowest.strategy == 'fault' else lowest.strategy} batches.** "
        f"Over the process states and measurements, the coverage is {100 * by_kind['other'].min():.0f}-"
        f"{100 * by_kind['other'].max():.0f} % for the recipe-driven, operator-controlled and APC batches and "
        f"{100 * by_kind['faulty'].min():.0f}-{100 * by_kind['faulty'].max():.0f} % for the faulty batches, which are "
        "the weakest part of the comparison.",
        "",
        "Inputs that follow the recipe in both data sets (unless PRBS, PAT control or a fault moves them) lie inside "
        "the band almost by construction; they are listed for completeness.",
        "",
    ]
    for group, channels in APPENDIX_CHANNELS.items():
        lines += [f"## {group[0].upper()}{group[1:]}", "",
                  "| channel | " + " | ".join(STRATEGIES) + " |", "|---" * (1 + len(STRATEGIES)) + "|"]  # fmt: skip
        for ch in channels:
            cells = []
            for strategy in STRATEGIES:
                r = env[(env.channel == ch) & (env.strategy == strategy)].iloc[0]
                cells.append(f"{r.inside} / {r.compared} ({100 * r.coverage:.0f} %)")
            lines.append(f"| {ch} | " + " | ".join(cells) + " |")
        lines.append("")
    (ROOT / "docs" / "validation_coverage.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args()
    df = load_process()
    plan = published_batches(df, load_statistics())
    t0 = time.perf_counter()
    sim_summary, results = simulate(plan, args.replicates, args.jobs)
    runtime = time.perf_counter() - t0
    env = envelope_table(df, sim_summary, results)
    inferred = fault_inference_table(df)

    lines = [
        "# Validation against the published IndPenSim 100-batch data set",
        "",
        f"Generated by `validation/compare_100_batches.py` with Penicillium {__version__}: {len(sim_summary)} simulated "
        f"batches ({args.replicates} replicates of the published campaign's structure) in {runtime:.0f} s. Data: "
        f"Goldrick (2019), [doi:{DOI}](https://doi.org/{DOI}), CC BY 4.0.",
        "",
        "Every simulated batch copies a published batch's control strategy, length and fault (the fault types are read "
        "from the inputs, see [below](#fault-types-of-the-published-faulty-batches)). Random streams differ from "
        "MATLAB's, so distributions are compared, not individual batches.",
        "",
        "## Yields",
        "",
        "| strategy | published mean ± sd [kg] | simulated mean ± sd [kg] | KS p-value | published final P [g/L] | simulated final P [g/L] | KS p-value |",
        "|---|---|---|---|---|---|---|",
    ]  # fmt: skip
    effects = []
    for strategy in STRATEGIES:
        p = plan[plan.strategy == strategy]
        s = sim_summary[sim_summary.strategy == strategy]
        ks_y = stats.ks_2samp(p.yield_kg, s.yield_kg).pvalue
        ks_p = stats.ks_2samp(p.final_P, s.final_P).pvalue
        lines.append(
            f"| {strategy} (n={len(p)} / {len(s)}) | {p.yield_kg.mean():.0f} ± {p.yield_kg.std():.0f} | "
            f"{s.yield_kg.mean():.0f} ± {s.yield_kg.std():.0f} | {ks_y:.2f} | {p.final_P.mean():.1f} ± {p.final_P.std():.1f} | "
            f"{s.final_P.mean():.1f} ± {s.final_P.std():.1f} | {ks_p:.2f} |"
        )
        diff, lo, hi = welch_interval(p.yield_kg, s.yield_kg)
        sd, mean = float(p.yield_kg.std()), float(p.yield_kg.mean())
        effects.append(
            f"| {strategy} | {diff:+.0f} ({100 * diff / mean:+.1f} %) | {lo:+.0f} to {hi:+.0f} | "
            f"{ks_power(len(p), len(s), sd, 0.05 * mean):.2f} | {detectable_shift(len(p), len(s), sd):.0f} |"
        )
    lines += [
        "",
        "The two-sample Kolmogorov-Smirnov (KS) test compares the whole distributions (location, spread and shape) and "
        "needs no assumption of normality. A p-value above 0.05 means that **no significant difference was detected** "
        "at the 5 % level, not that the distributions are equal: with 30 published batches per strategy (10 with "
        "faults) the test has low power, as the next table shows.",
        "",
        "### Size of the differences",
        "",
        "Supplementary to the KS test: the mean yield difference (simulated minus published) with its 95 % Welch "
        "interval, and the power of the KS test at these sample sizes, computed from the published summary statistics "
        "(normal yields with the published standard deviation): the probability of detecting a shift of the mean by "
        "5 % of the published mean, and the shift it detects with 80 % probability.",
        "",
        "| strategy | mean difference [kg] | 95 % Welch interval [kg] | KS power, 5 % shift | shift detected with 80 % power [kg] |",
        "|---|---|---|---|---|",
        *effects,
        "",
        "## Trajectory envelopes",
        "",
        "Coverage: share of published samples inside the simulated 5-95 % band at the same time (up to the shortest "
        "batch of each strategy); about 0.9 is expected when the two distributions agree. Median gap: mean absolute "
        "difference between the published and simulated median trajectories, relative to the channel's 99th "
        "percentile. The samples of one batch are strongly correlated in time, so with 30 published batches per "
        "strategy (10 with faults) the coverage of a band varies by several percentage points by chance. Every "
        "channel, with the number of samples inside the band and compared, is in the "
        "[coverage appendix](validation_coverage.md); some channels not shown here have lower coverage, the lowest "
        "being the vessel weight `Wt` in the faulty batches (see the appendix for its value).",
        "",
    ]  # fmt: skip
    pivot_cov = env.pivot(index="channel", columns="strategy", values="coverage").loc[CHANNELS, list(STRATEGIES)]
    pivot_gap = env.pivot(index="channel", columns="strategy", values="median_gap").loc[CHANNELS, list(STRATEGIES)]
    lines.append("| channel | " + " | ".join(f"{s} coverage" for s in STRATEGIES) + " | " + " | ".join(f"{s} median gap" for s in STRATEGIES) + " |")  # fmt: skip
    lines.append("|---" * (1 + 2 * len(STRATEGIES)) + "|")
    for ch in CHANNELS:
        cov = " | ".join(f"{pivot_cov.loc[ch, s]:.2f}" for s in STRATEGIES)
        gap = " | ".join(f"{pivot_gap.loc[ch, s]:.3f}" for s in STRATEGIES)
        lines.append(f"| {ch} | {cov} | {gap} |")
    lines += ["", "![envelopes](img/validation_100_batches.png)", ""]
    lines += [
        "## Fault types of the published faulty batches",
        "",
        "The published data set flags the faulty samples (`Fault_ref`) but does not name the fault type, so the type "
        "is read from the inputs. Each IndPenSim process fault holds one input at a fixed value over fixed sample "
        "windows ([Faults](faults.md#faults)), for example the aeration at 20 m³/min over samples 100-120 (20-24 h). "
        "For each of batches 91 to 100, exactly one of these signatures matches on every sample of its windows, and "
        "none of the other process faults matches on any sample. As an independent check, the samples with "
        "`Fault_ref` = 1 coincide with the window schedule of the assigned fault. Sensor drifts leave no signature in "
        "the inputs and could not be identified this way, but none of the ten batches needs that case.",
        "",
        "There is no published label to measure the accuracy of this method against; it rests on the fingerprint of "
        "each fault (the input involved, its value and the start of its windows), and all ten batches are taken as "
        "correctly identified.",
        "",
        "| batch | assigned fault | signal | samples matching, all windows | samples matching another fault | `Fault_ref` matches the schedule |",
        "|---|---|---|---|---|---|",
        *(f"| {r.batch_id} | {Fault(r.fault).name} | {r.signal} | {r.matching} | {r.other_matches} | "
          f"{'yes' if r.fault_ref_agrees else 'no'} |" for r in inferred.itertuples()),
        "",
        "In total: " + ", ".join(f"{n} {Fault(f).name}" for f, n in inferred.fault.value_counts().items()) + ".",
        "",
    ]  # fmt: skip
    out = ROOT / "docs" / "validation_100_batches.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    write_coverage_appendix(
        envelope_table(df, sim_summary, results, [ch for group in APPENDIX_CHANNELS.values() for ch in group])
    )
    plot(df, sim_summary, results, ROOT / "docs" / "img" / "validation_100_batches.png")
    sim_summary.to_csv(ROOT / "validation" / "compare_100_batches_simulated.csv", index=False)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
