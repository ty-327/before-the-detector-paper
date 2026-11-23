"""
Before the Detector: Can Public Gaming Data Expose the Hidden Laundromat?
CS:GO / CS2 Player Count and Key Trading Volume Analysis
"""

import os
import urllib.parse
import pandas as pd
import plotly.graph_objects as go
from PIL import Image
import kagglehub

# =============================================================================
# 1. CONFIGURATION & USER SETTINGS
# Reviewers: Modify these paths and parameters as needed for your environment
# =============================================================================

# File paths
# Get the exact absolute path of the folder where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Build the path to the data folder
STEAMDB_CSV_PATH = os.path.join(SCRIPT_DIR, "data", "steamdb_chart_730.csv")
KAGGLE_DATASET = "kieranpoc/counter-strike-market-sale-data"

# Analysis Timeframe Cutoffs
CUTOFF_START_DATE = "2013-10-01"
CUTOFF_END_DATE = "2021-01-01"

# Output Filenames
CHART_1_OUTPUT = "weekly player count vs key trading volume.png"
CHART_2_OUTPUT = "weekly key trade volume per player ratio.png"

# =============================================================================

print("Downloading CS:GO market sale data from Kaggle...")
kaggle_path = kagglehub.dataset_download(KAGGLE_DATASET)
items_dir = os.path.join(kaggle_path, "items")
items_files = os.listdir(items_dir)

clean_items_files = [urllib.parse.unquote(f) for f in items_files]
clean_to_raw_map = {clean.lower(): raw for clean, raw in zip(clean_items_files, items_files)}

all_cs2_keys = [
    "Kilowatt Case Key", "Dreams & Nightmares Case Key", "Revolution Case Key",
    "Fever Case Key", "Operation Hydra Case Key", "Recoil Case Key",
    "Chroma Case Key", "Snakebite Case Key", "Danger Zone Case Key",
    "Prisma Case Key", "CS20 Case Key", "CS:GO Case Key", "Glove Case Key",
    "Chroma 3 Case Key", "Operation Wildfire Case Key", "Horizon Case Key",
    "Operation Breakout Case Key", "eSports Key", "Spectrum Case Key",
    "Gamma 2 Case Key", "Chroma 2 Case Key", "Clutch Case Key",
    "Fracture Case Key", "Huntsman Case Key", "CS:GO Capsule Key",
    "Prisma 2 Case Key", "Shattered Web Case Key", "Shadow Case Key",
    "Gamma Case Key", "Winter Offensive Case Key", "Gallery Case Key",
    "Community Sticker Capsule 1 Key", "Operation Phoenix Case Key",
    "Operation Riptide Case Key", "Operation Broken Fang Case Key",
    "Spectrum 2 Case Key", "Revolver Case Key", "Falchion Case Key",
    "Operation Vanguard Case Key",
]

found_keys = []
for key_name in all_cs2_keys:
    matched_raw_file = next((raw for clean, raw in clean_to_raw_map.items() if key_name.lower() in clean), None)
    if matched_raw_file:
        found_keys.append((key_name, matched_raw_file))

print(f"Loaded {len(found_keys)} out of {len(all_cs2_keys)} CS2 keys from dataset.")

key_dfs = {}
for clean_name, raw_filename in found_keys:
    file_path = os.path.join(items_dir, raw_filename)
    df = pd.read_csv(file_path)
    df["item_name"] = clean_name
    key_dfs[clean_name] = df

# -----------------------------------------------------------------------------
# 2. AGGREGATE MARKET DATA
# -----------------------------------------------------------------------------
master_keys_df = pd.concat(key_dfs.values(), ignore_index=True)
master_keys_df["date"] = pd.to_datetime(master_keys_df["unix timestamp"], unit="s")
master_keys_df["day"] = master_keys_df["date"].dt.date
master_keys_df["daily_value"] = master_keys_df["price"] * master_keys_df["quantity"]

aggregated_key_df = (
    master_keys_df.groupby("day")
    .agg(
        total_volume=("quantity", "sum"),
        total_value=("daily_value", "sum"),
        simple_avg_price=("price", "mean"),
        keys_traded=("item_name", "nunique"),
    )
    .reset_index()
)

aggregated_key_df["weighted_avg_price"] = aggregated_key_df["total_value"] / aggregated_key_df["total_volume"]
aggregated_key_df.rename(columns={"day": "date"}, inplace=True)
aggregated_key_df["date"] = pd.to_datetime(aggregated_key_df["date"])
aggregated_key_df = aggregated_key_df.sort_values(by="date")

# -----------------------------------------------------------------------------
# 3. LOAD STEAMDB PLAYER DATA
# -----------------------------------------------------------------------------
if not os.path.exists(STEAMDB_CSV_PATH):
    raise FileNotFoundError(f"Could not locate '{STEAMDB_CSV_PATH}'. Please verify the path in the Configuration block.")

players_df = pd.read_csv(STEAMDB_CSV_PATH)
players_df.columns = players_df.columns.astype(str).str.strip()

players_df["DateTime"] = pd.to_datetime(players_df["DateTime"], errors="coerce")
players_df["Players"] = pd.to_numeric(players_df["Players"], errors="coerce")
players_df["Average Players"] = pd.to_numeric(players_df["Average Players"], errors="coerce")
players_df = players_df.dropna(subset=["DateTime"]).copy()
players_df["date"] = players_df["DateTime"].dt.normalize()

daily_players_df = (
    players_df.groupby("date", as_index=False)
    .agg(peak_players=("Players", "max"), avg_players=("Average Players", "mean"))
    .sort_values("date")
    .reset_index(drop=True)
)

# -----------------------------------------------------------------------------
# 4. MERGE & RESAMPLE TO WEEKLY FREQUENCY
# -----------------------------------------------------------------------------
combined_df = pd.merge(aggregated_key_df, daily_players_df, on="date", how="outer").sort_values(by="date")
combined_df["date"] = pd.to_datetime(combined_df["date"])

cutoff_start = pd.to_datetime(CUTOFF_START_DATE)
cutoff_end = pd.to_datetime(CUTOFF_END_DATE)

weekly_df = combined_df[
    (combined_df["date"] >= cutoff_start) & (combined_df["date"] < cutoff_end)
].reset_index(drop=True)

weekly_df = (
    weekly_df.resample("W-MON", on="date")
    .agg({"peak_players": "max", "total_volume": "sum"})
    .reset_index()
)

# -----------------------------------------------------------------------------
# 5. CHART 1: WEEKLY PLAYERS VS KEY TRADING VOLUME
# -----------------------------------------------------------------------------
fig_combined = go.Figure()

fig_combined.add_trace(go.Scatter(
    x=weekly_df["date"], y=weekly_df["peak_players"], mode="lines",
    name="Weekly Peak Players", line=dict(color="#1f77b4", width=2.6), yaxis="y1"
))

fig_combined.add_trace(go.Scatter(
    x=weekly_df["date"], y=weekly_df["total_volume"], mode="lines",
    name="Weekly Volume Traded", line=dict(color="#ff7f0e", width=2.0),
    fill="tozeroy", fillcolor="rgba(255, 127, 14, 0.12)", yaxis="y2"
))

LABEL_FONT_SIZE = 29
BOX_PADDING = 9
BOX_BORDER_WIDTH = 2.5
STEM_LINE_WIDTH = 3

ban_date = pd.to_datetime("2019-10-28")
fig_combined.add_vline(x=ban_date.timestamp() * 1000, line_width=3.5, line_dash="dash", line_color="#d62728")
fig_combined.add_annotation(
    x=ban_date, y=0.97, yshift=50, xref="x", yref="paper",
    text="<b>Valve Key Trade Ban</b><br>(Oct 28, 2019)", showarrow=False,
    xanchor="center", yanchor="top", font=dict(size=31, color="#d62728"),
    bgcolor="rgba(255, 255, 255, 0.98)", bordercolor="#d62728",
    borderwidth=BOX_BORDER_WIDTH, borderpad=BOX_PADDING
)

def add_sub_axis_event(fig, date_str, label_text, color="#444444", y_offset=-0.18, xshift=0):
    event_date = pd.to_datetime(date_str)
    fig.add_shape(
        type="line", x0=event_date, x1=event_date, y0=0, y1=y_offset + 0.02,
        xref="x", yref="paper", line=dict(color=color, width=STEM_LINE_WIDTH), opacity=0.65
    )
    fig.add_annotation(
        x=event_date, y=y_offset, xshift=xshift, xref="x", yref="paper",
        text=f"<b>{label_text}</b><br>({event_date.strftime('%b %d, %Y')})",
        showarrow=False, xanchor="center", yanchor="top", font=dict(size=LABEL_FONT_SIZE, color=color),
        bgcolor="rgba(255, 255, 255, 0.98)", bordercolor=color,
        borderwidth=BOX_BORDER_WIDTH, borderpad=BOX_PADDING
    )

add_sub_axis_event(fig_combined, "2016-07-19", "Valve Gambling Cease & Desist", "#d95f02", y_offset=-0.18, xshift=-160)
add_sub_axis_event(fig_combined, "2018-01-28", "Boston Major Finals", "#9467bd", y_offset=-0.18)
add_sub_axis_event(fig_combined, "2018-02-14", "Clutch Case Released", "#17becf", y_offset=-0.42)
add_sub_axis_event(fig_combined, "2018-03-29", "Valve Adds 7-Day Trade Lock", "#2ca02c", y_offset=-0.66)
add_sub_axis_event(fig_combined, "2019-08-13", "Argentina Peso Crash", "#e377c2", y_offset=-0.18, xshift=100)

fig_combined.update_layout(
    title=dict(
        text="<b>CS:GO Weekly Player Count vs. Key Trading Volume</b>",
        font=dict(size=40),
    ),
    width=1950,
    height=1330,
    template="plotly_white",
    hovermode="x unified",
    margin=dict(l=160, r=160, t=220, b=530),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.08,
        xanchor="right",
        x=1,
        font=dict(size=34),
    ),
    yaxis=dict(
        title=dict(text="<b>Weekly Peak Players</b>", font=dict(color="#1f77b4", size=36)),
        tickfont=dict(color="#1f77b4", size=32),
        tickformat=",.0f",
        side="left",
        showgrid=True,
    ),
    # --- AXIS 2 (RIGHT): VOLUME ---
    yaxis2=dict(
        title=dict(text="<b>Weekly Volume Traded</b>", font=dict(color="#ff7f0e", size=36)),
        tickfont=dict(color="#ff7f0e", size=32),
        tickformat=",.0f",
        side="right",
        overlaying="y",
        showgrid=False,
        range=[0, 1200000],
    ),
    xaxis=dict(
        title=dict(text="<b>Year</b>", font=dict(size=36)),
        tickfont=dict(color="#444444", size=32),
        showgrid=True,
    ),
)

# -----------------------------------------------------------------------------
# 6. CHART 2: VOLUME PER PLAYER RATIO
# -----------------------------------------------------------------------------
weekly_df["volume_per_player"] = weekly_df["total_volume"] / weekly_df["peak_players"]

fig_ratio = go.Figure()
fig_ratio.add_trace(go.Scatter(
    x=weekly_df["date"], y=weekly_df["volume_per_player"], mode="lines",
    name="Volume per Player", line=dict(color="#2ca02c", width=2.6),
    fill="tozeroy", fillcolor="rgba(44, 160, 44, 0.1)"
))

fig_ratio.add_vline(x=ban_date.timestamp() * 1000, line_width=3.5, line_dash="dash", line_color="#d62728")
fig_ratio.add_annotation(
    x=ban_date, y=0.97, yshift=60, xref="x", yref="paper",
    text="<b>Valve Key Trade Ban</b><br>(Oct 28, 2019)", showarrow=False,
    xanchor="center", yanchor="top", font=dict(size=34, color="#d62728"),
    bgcolor="rgba(255, 255, 255, 0.98)", bordercolor="#d62728", borderwidth=3.0, borderpad=10
)

fig_ratio.update_layout(
    title=dict(text="<b>CS:GO Weekly Key Trade Volume per Player</b>", font=dict(size=40)),
    width=1950, height=850, template="plotly_white", hovermode="x unified",
    legend=dict(font=dict(size=30)), 
    
    # NEW SYNTAX FOR Y-AXIS
    yaxis=dict(
        title=dict(text="<b>Trades per Player</b>", font=dict(size=36)), 
        tickfont=dict(size=32)
    ),
    
    # NEW SYNTAX FOR X-AXIS
    xaxis=dict(
        title=dict(text="<b>Year</b>", font=dict(size=36)), 
        tickfont=dict(size=32)
    ),
    
    margin=dict(l=150, r=80, t=200, b=120)
)

# -----------------------------------------------------------------------------
# 7. EXPORT HIGH-RESOLUTION IMAGES
# -----------------------------------------------------------------------------
def save_high_res_fig(fig, filename, w, h):
    fig.write_image(filename, width=w, height=h, scale=5)
    img = Image.open(filename)
    img.save(filename, dpi=(1000, 1000))
    print(f"Saved: {filename}")

print("Generating high-resolution charts...")
save_high_res_fig(fig_combined, CHART_1_OUTPUT, 1950, 1330)
save_high_res_fig(fig_ratio, CHART_2_OUTPUT, 1950, 850)
print("Analysis complete.")