# Macro Market Trends: Key Trading vs. Player Count

This module contains the Python script and dataset used to evaluate macro-level trends in key trading volume vs player count. It creates two visual plots which compare the historical trading volume of Counter-Strike case keys against the player count.

## Folder Structure

*   `analysis.py`: The single, standalone Python script that downloads Kaggle market data, merges it with local SteamDB player counts, and generates the two plots.
*   `data/`
    *   `steamdb_chart_730.csv`: A static snapshot of the historical daily player count used as the baseline for routine activity metrics.

## Prerequisites

To execute this script, you will need Python 3.8+ and the following libraries:

```bash
pip install pandas plotly kaleido pillow kagglehub
```

## Configuration

At the very top of `analysis.py`, there is a **Configuration & User Settings** block. You can use this section to adjust:
*   **File Paths:** If you move the `steamdb_chart_730.csv` file, update the `STEAMDB_CSV_PATH` variable.
*   **Timeframes:** The `CUTOFF_START_DATE` and `CUTOFF_END_DATE` variables control the analysis window.
*   **Output Names:** The filenames for the generated `.png` charts.

By default, the script is configured to run out-of-the-box assuming this folder's structure remains intact.

## How to Run

1.  Open your terminal or command prompt.
2.  Navigate into this specific module's directory:
3.  Execute the analysis script:
    ```bash
    python analysis.py
    ```

### What to Expect

Upon execution, the script will:
1. Use `kagglehub` to download the raw Counter-Strike market sale dataset (over 22,000 files).
2. Dynamically search for and extract the historical ledgers for all 39 relevant CS:GO/CS2 case keys.
3. Merge this financial data with the local `steamdb_chart_730.csv` file and resample the data into a weekly timeframe.
4. Calculate the trades-per-player ratio to highlight irregular volume spikes.

**Output:** The script will generate two high-resolution `.png` files directly in this folder, which mirror the two historical key volume plots in the H1 section of the results in the manuscript.