"""Regenerate the README figure: key trajectories of one default batch.

    pip install "penicillium[fast]" matplotlib
    python docs/scripts/readme_figure.py

Writes docs/assets/readme_batch.png (1200 x 600 px). Channel descriptions and units come from
``penicillium.CHANNELS``, the metadata of every ``BatchResult`` channel.
"""

from pathlib import Path

import matplotlib.pyplot as plt

from penicillium import CHANNELS, Simulator

OUT = Path(__file__).resolve().parents[1] / "assets" / "readme_batch.png"
SEED = 1
# Channels per panel; channels in one panel share a unit.
PANELS = [["P"], ["X"], ["S"], ["Fs", "Foil", "Fpaa"]]
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"


def main() -> None:
    result = Simulator().run(seed=SEED)
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK})
    fig, axes = plt.subplots(2, 2, figsize=(12, 6), dpi=100, sharex=True, facecolor=SURFACE)
    for ax, names in zip(axes.flat, PANELS, strict=True):
        title = CHANNELS[names[0]][0] if len(names) == 1 else "Feed rates"
        units = {CHANNELS[name][1] for name in names}
        assert len(units) == 1, f"channels {names} have different units: {units}"
        for colour, name in zip(COLOURS, names, strict=False):
            ax.plot(result.time, result[name], color=colour, linewidth=1.6, label=f"{CHANNELS[name][0]} ({name})")
        ax.set_facecolor(SURFACE)
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_ylabel(f"{names[0]} ({units.pop()})" if len(names) == 1 else f"Feed rate ({units.pop()})")
        ax.grid(color="#e4e3df", linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(colors=MUTED)
        if len(names) > 1:
            ax.legend(frameon=False, fontsize=9, loc="upper right")
    for ax in axes[1]:
        ax.set_xlabel("Time (h)")
    fig.suptitle(
        f"One default batch, Simulator().run(seed={SEED}): {result.time[-1]:.0f} h, "
        f"{result.total_yield:,.0f} kg penicillin harvested",
        x=0.01,
        ha="left",
        fontsize=12,
    )
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=100, facecolor=SURFACE)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
