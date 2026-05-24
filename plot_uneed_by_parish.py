"""
plot_uneed_by_parish.py
─────────────────────────────────────────────────────────
Group the file index_UNEED.csv by parish, compute the mean
of each (sub)-index, and draw a grouped bar chart. Place 
the legend outside the plot.

Author: Thiago C. Jesus
Part of the UNEED microgrid-positioning framework (MIT License).
"""

# ------------------------------------------------------------------
# IMPORTS
# ------------------------------------------------------------------
from pathlib import Path
from typing   import Final, List
import re

import numpy  as np
import pandas as pd
import matplotlib.pyplot as plt

# ------------------------------------------------------------------
# CONSTANTS
# ------------------------------------------------------------------
INDEX_DIR:    Final[Path] = Path("datasets") / "indexes"
INPUT_CSV:    Final[Path] = INDEX_DIR / "index_UNEED.csv"

FIG_SIZE:     Final[tuple[int, int]] = (14, 6)
BAR_WIDTH:    Final[float] = 0.13

'''
COLORS:       Final[List[str]] = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
    "#ff7f00", "#ffff33", "#a65628"
]
'''
'''# Pastel colours (ColorBrewer-inspired)
COLORS:       Final[List[str]] = [
    "#fbb4ae",  # pastel red
    "#b3cde3",  # pastel blue
    "#ccebc5",  # pastel green
    "#decbe4",  # pastel purple
    "#fed9a6",  # pastel orange
    "#ffffcc",  # pastel yellow
    "#e5d8bd"   # pastel brown
]
'''
# Pastel colours – slightly darker for better visibility
COLORS:       Final[List[str]] = [
    #"#e79c9c",  # deeper pastel red
    "#7faac9",  # deeper pastel blue
    "#90c79d",  # deeper pastel green
    "#b99ac9",  # deeper pastel purple
    "#f5b47e",  # deeper pastel orange
    "#fff68f",  # deeper pastel yellow
    "#c8b49a"   # deeper pastel brown
]
Y_LABEL:      Final[str] = "Sub-Index value"

# Font sizes --------------------------------------------------------
TITLE_SIZE:   Final[int] = 20
LABEL_SIZE:   Final[int] = 16
TICK_SIZE:    Final[int] = 14
LEGEND_SIZE:  Final[int] = 14

# ------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------
def load_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found.")
    return pd.read_csv(csv_path)


def compute_means(df: pd.DataFrame) -> pd.DataFrame:
    '''metrics = [
        "UNEED", "RenewPot", "EmgVuln", "PriorInfra",
        "HeatInfra", "HeatLoad", "SocEcon"
    ]'''
    metrics = [
        "RenewPot", "EmgVuln", "PriorInfra",
        "HeatInfra", "HeatLoad", "SocEcon"
    ]
    return (
        df.groupby("parish")[metrics]
          .mean()
          .sort_index()
          .round(5)
    )


def _clean_first_word(name: str) -> str:
    """Return the first word of *name* without trailing punctuation and with the first letter capitalised."""
    first = name.split()[0]
    # Remove any trailing punctuation such as commas, semicolons, periods, or colons
    first = re.sub(r"[,:;.!?]+$", "", first)
    return first.capitalize()


def plot_grouped_bars(df_means: pd.DataFrame) -> None:
    """Plot grouped bar chart using cleaned first words of parish names."""

    parishes_full: List[str] = df_means.index.to_list()
    parishes: List[str] = [_clean_first_word(p) for p in parishes_full]

    metrics: List[str] = df_means.columns.to_list()
    n_parish  = len(parishes)
    n_metric  = len(metrics)

    indices   = np.arange(n_parish)

    fig, ax = plt.subplots(figsize=FIG_SIZE)

    for i, metric in enumerate(metrics):
        positions = indices + (i - (n_metric - 1) / 2) * BAR_WIDTH
        ax.bar(
            positions,
            df_means[metric],
            width=BAR_WIDTH,
            label=metric,
            color=COLORS[i % len(COLORS)],
            edgecolor="black"
        )

    # Axis / labels -------------------------------------------------
    ax.set_ylabel(Y_LABEL, fontsize=LABEL_SIZE)
    ax.set_xticks(indices)
    ax.set_xticklabels(parishes, rotation=20, ha="right", fontsize=TICK_SIZE)
    ax.tick_params(axis="y", labelsize=TICK_SIZE)
    ax.set_ylim(0, 1)
    #ax.set_title("Mean normalised indices per parish – Porto", fontsize=TITLE_SIZE)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    # Legend: outside, on top --------------------------------------
    ax.legend(
        ncol=1,
        fontsize=LEGEND_SIZE,
        loc="upper left",
        bbox_to_anchor=(1.0, 1.0),
        frameon=False
    )



    fig.tight_layout()
    plt.show()


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main() -> None:
    df_raw   = load_data(INPUT_CSV)
    df_means = compute_means(df_raw)
    plot_grouped_bars(df_means)


if __name__ == "__main__":
    main()
