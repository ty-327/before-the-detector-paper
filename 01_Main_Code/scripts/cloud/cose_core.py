"""Reconstructed COSE numerical tools. Created 2026-11-12, NOT recovered final code.

The caller supplies the recovered daily panel. No item membership is inferred or
retuned here. Missing observations remain missing. See METHODS.md for conventions.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import lsmr

VERSION = "rebuild-1.0.0"
BAN = pd.Timestamp("2019-10-28", tz="UTC")
WINDOWS = {"legacy21": (21, 22), "tight21": (21, 21), "legacy90": (90, 91)}
ARM_MAP = {"substitute": "candidate", "candidate": "candidate", "control": "control", "key": "key"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, np.ndarray):
        return clean_json(value.tolist())
    return value


def save_json(path: Path, value: Any) -> None:
    Path(path).write_text(json.dumps(clean_json(value), indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_panel(path: Path) -> tuple[pd.DataFrame, dict]:
    """Read an already-assigned panel; fail rather than silently repair its data."""
    path = Path(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        d = pd.read_parquet(path)
    else:
        cols = pd.read_csv(path, nrows=0).columns.tolist()
        use = [c for c in ("day", "item", "units", "arm", "vwap", "price") if c in cols]
        d = pd.read_csv(path, usecols=use)
    required = {"day", "item", "units", "arm"}
    if not required.issubset(d.columns):
        raise ValueError(f"Panel must have {sorted(required)}; found {list(d.columns)}. Raw histories are not this input.")
    if d[list(required)].isna().any().any():
        raise ValueError("Missing required fields. Audit upstream; no rows silently dropped.")
    d["item"] = d["item"].astype(str)
    if d["item"].str.strip().eq("").any():
        raise ValueError("Blank item name.")
    original_arms = d["arm"].astype(str).str.strip().str.lower()
    unknown = sorted(set(original_arms) - set(ARM_MAP))
    if unknown:
        raise ValueError(f"Unknown arms {unknown}. Supply the final assigned panel, not candidate eligibility labels.")
    d["arm"] = original_arms.map(ARM_MAP)
    d["day"] = pd.to_datetime(d["day"], utc=True, errors="raise")
    if not d["day"].equals(d["day"].dt.floor("D")):
        raise ValueError("Input is not a midnight-UTC daily panel. Aggregation must be audited upstream.")
    d["units"] = pd.to_numeric(d["units"], errors="raise")
    if not np.isfinite(d["units"].to_numpy(float)).all() or (d["units"] < 0).any():
        raise ValueError("Units must be finite and nonnegative.")
    dup = d.duplicated(["item", "day"], keep=False)
    if dup.any():
        raise ValueError(f"{int(dup.sum())} rows participate in duplicate item-days. No automatic summing/deduplication.")
    if d.groupby("item", sort=False)["arm"].nunique().max() != 1:
        raise ValueError("An item's assigned arm changes over time.")
    d = d.sort_values(["day", "item"], kind="mergesort").reset_index(drop=True)
    manifest = {"input_name": path.name, "input_sha256": sha256(path), "rows": len(d),
                "items": d["item"].nunique(), "start": d["day"].min(), "end": d["day"].max(),
                "items_by_arm": d.groupby("arm")["item"].nunique().to_dict(),
                "rows_by_arm": d.groupby("arm").size().to_dict(),
                "zero_unit_rows": int(d["units"].eq(0).sum()),
                "fractional_unit_rows": int((d["units"] % 1 != 0).sum()),
                "membership": "Preserved from input arm column; not reconstructed from names or manuscript counts.",
                "scope": "Daily-panel checks only, not validation of raw currency, aggregation or source completeness."}
    return d, manifest


def subset_panel(d: pd.DataFrame, items_file: Path | None) -> tuple[pd.DataFrame, dict]:
    """Exclude an explicit, analyst-verified container list, not a name heuristic."""
    if items_file is None:
        return d, {"subset": "all_candidates", "excluded_candidates": 0}
    x = pd.read_csv(items_file)
    if "item" not in x.columns or x["item"].isna().any() or x["item"].duplicated().any():
        raise ValueError("Exclusion CSV must have a unique nonmissing item column.")
    names = set(x["item"].astype(str))
    actual = set(d.loc[d.arm == "candidate", "item"])
    if not names or not names.issubset(actual):
        raise ValueError(f"Exclusions must be present candidate items; unmatched {sorted(names-actual)[:10]}.")
    return d.loc[~d.item.isin(names)].copy(), {
        "subset": "explicit_container_exclusion", "excluded_candidates": len(names),
        "excluded_items": sorted(names), "exclusion_file_sha256": sha256(items_file)}


def event_window(d: pd.DataFrame, date: pd.Timestamp, window: str) -> pd.DataFrame:
    pre, post = WINDOWS[window]
    lo, hi = date - pd.Timedelta(days=pre), date + pd.Timedelta(days=post-1)
    return d.loc[d.arm.isin(["candidate", "control"]) & d.day.between(lo, hi)].copy().reset_index(drop=True)


def window_audit(d: pd.DataFrame, date: pd.Timestamp, window: str) -> dict:
    z = event_window(d, date, window)
    pre, post = WINDOWS[window]
    if z.empty:
        return {"window": window, "rows": 0}
    rows = z.groupby("item").size()
    return {"window": window, "event_date": date, "start": date-pd.Timedelta(days=pre),
            "end": date+pd.Timedelta(days=post-1), "nominal_pre_days": pre, "nominal_post_days": post,
            "event_day_is_post": True, "rows": len(z), "items": len(rows),
            "observed_calendar_days": z.day.nunique(),
            "complete_items": int(rows.eq(pre+post).sum()),
            "potential_unobserved_item_days": int(len(rows)*(pre+post)-len(z)),
            "missingness_note": "Potential missing cells, not asserted zero sales; may include item entry/exit.",
            "pre_rows": int((z.day < date).sum()), "post_rows": int((z.day >= date).sum()),
            "items_by_arm": z.groupby("arm").item.nunique().to_dict()}


def _demean(v: np.ndarray, codes: np.ndarray, size: int) -> np.ndarray:
    n = np.bincount(codes, minlength=size)
    m = np.bincount(codes, weights=v, minlength=size) / n
    return v-m[codes]


class Design:
    """Full-rank absorbed OLS and exact cached coefficient weights.

    item_post: item effects + common post + candidate*post.
    twfe: item effects + unrestricted date effects + candidate*post.
    """
    def __init__(self, d: pd.DataFrame, date: pd.Timestamp, model: str):
        self.d = d.reset_index(drop=True).copy()
        self.date, self.model = date, model
        if model not in {"item_post", "twfe"}:
            raise ValueError(f"Unknown model: {model}")
        self.n = len(d)
        self.ii, self.items = pd.factorize(self.d.item, sort=True)
        self.tt, self.dates = pd.factorize(self.d.day, sort=True)
        self.ni, self.nt = len(self.items), len(self.dates)
        self.post = (self.d.day >= date).to_numpy(float)
        self.treat = self.d.arm.eq("candidate").to_numpy(float)
        if self.ni < 2 or self.nt < 2 or len(np.unique(self.treat)) != 2 or len(np.unique(self.post)) != 2:
            raise ValueError("Need both groups and both periods with at least two items and dates.")
        if any(not np.any((self.treat == g) & (self.post == p)) for g in (0, 1) for p in (0, 1)):
            raise ValueError("At least one group-period is absent.")
        self.x = self.treat*self.post
        self.projection_iterations = []
        if model == "item_post":
            self.p_within = _demean(self.post, self.ii, self.ni)
            self.p_norm = float(self.p_within @ self.p_within)
            if self.p_norm <= 1e-12:
                raise ValueError("No within-item pre/post variation.")
            self.rank_nuisance = self.ni+1
            self.z = None
        else:
            row = np.arange(self.n)
            self.z = sparse.coo_matrix((np.ones(2*self.n),
                        (np.r_[row,row], np.r_[self.ii, self.ni+self.tt])),
                        shape=(self.n, self.ni+self.nt)).tocsr()
            adj = sparse.coo_matrix((np.ones(2*self.n),
                       (np.r_[self.ii, self.ni+self.tt],np.r_[self.ni+self.tt,self.ii])),
                       shape=(self.ni+self.nt,self.ni+self.nt)).tocsr()
            components = connected_components(adj, directed=False, return_labels=False)
            self.rank_nuisance = self.ni+self.nt-components
        self.rx = self.residualize(self.x)
        self.sxx = float(self.rx @ self.rx)
        if self.sxx <= 1e-10:
            raise ValueError("Candidate-by-post effect is unidentified after absorbing nuisance effects.")
        self.weights = self.rx / self.sxx
        self.k = self.rank_nuisance+1
        if self.n <= self.k:
            raise ValueError("No residual degrees of freedom.")

    def residualize(self, v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, float)
        if v.shape != (self.n,) or not np.isfinite(v).all():
            raise ValueError("Outcome shape or finite-value check failed.")
        if self.model == "item_post":
            u = _demean(v, self.ii, self.ni)
            return u-self.p_within*float(self.p_within @ u)/self.p_norm
        sol = lsmr(self.z, v, atol=1e-12, btol=1e-12, maxiter=10000, conlim=1e12)
        self.projection_iterations.append(int(sol[2]))
        if sol[1] not in (0, 1, 2, 4, 5):
            raise RuntimeError(f"Fixed-effect projection failed (LSMR stop code {sol[1]}).")
        r = v-self.z @ sol[0]
        # Normalized orthogonality, independently of solver stop criterion.
        col_norm = np.sqrt(np.asarray(self.z.power(2).sum(axis=0)).ravel())
        orth = np.max(np.abs(self.z.T @ r)/np.maximum(col_norm, 1))
        if orth > 1e-7*max(1., np.linalg.norm(v)):
            raise RuntimeError(f"Fixed-effect orthogonality check failed: {orth}")
        return r

    def beta(self, y: np.ndarray) -> float:
        return float(self.weights @ np.asarray(y, float))

    def _cluster_var(self, score: np.ndarray, codes: np.ndarray, g: int) -> float:
        if g < 2:
            return float("nan")
        scores = np.bincount(codes, weights=score, minlength=g)
        correction = (g/(g-1))*((self.n-1)/(self.n-self.k))
        return float(correction*(scores @ scores))

    def fit(self, y: np.ndarray | None = None) -> dict:
        if y is None:
            y = np.log1p(self.d.units.to_numpy(float))
        y = np.asarray(y, float)
        ry = self.residualize(y)
        b = self.beta(y)
        resid = ry-self.rx*b
        score = self.weights*resid
        vi = self._cluster_var(score, self.ii, self.ni)
        vt = self._cluster_var(score, self.tt, self.nt)
        # Item-days are unique by loader, so intersection clusters are rows.
        vb = self._cluster_var(score, np.arange(self.n), self.n)
        v2 = vi+vt-vb
        return {"coefficient": b, "transformed_contrast_pct": float(np.expm1(b)*100),
                "se_item": math.sqrt(vi) if vi >= 0 else float("nan"),
                "se_date": math.sqrt(vt) if vt >= 0 else float("nan"),
                "se_item_date": math.sqrt(v2) if v2 >= 0 else float("nan"),
                "two_way_variance_negative": bool(v2 < 0),
                "rows": self.n, "items": self.ni, "dates": self.nt,
                "rank_parameters": self.k, "model": self.model,
                "small_sample_correction": "G/(G-1) * (N-1)/(N-K), full-rank K including absorbed effects",
                "percent_note": "100*expm1(beta) is a log(1+units) transformed contrast, not aggregate unit change or a causal effect.",
                "y": y, "residual": resid, "fitted": y-resid,
                "null_residual": ry, "null_fitted": y-ry}


def public_fit(fit: dict) -> dict:
    return {k:v for k,v in fit.items() if k not in {"y","residual","fitted","null_residual","null_fitted"}}


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float,float]:
    if not (0 <= k <= n and n > 0):
        raise ValueError("Bad binomial counts.")
    p = k/n
    den = 1+z*z/n
    center = (p+z*z/(2*n))/den
    half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return float(max(0, center-half)),float(min(1,center+half))


def floor_brackets(grid: np.ndarray, rates: np.ndarray, lows: np.ndarray,
                   highs: np.ndarray, target: float=.8) -> dict:
    """Grid crossing only. Never extrapolate, force monotonicity, or target 30/44."""
    grid, rates = np.asarray(grid), np.asarray(rates)
    def crossing(values):
        ix = np.flatnonzero(np.asarray(values) >= target)
        if not len(ix):
            return None, None
        j = int(ix[0])
        return float(grid[j-1]) if j else 0., float(grid[j])
    lower, upper = crossing(rates)
    _, possible = crossing(highs)
    _, conservative = crossing(lows)
    return {"target_recovery": target, "crossing_lower_grid_pct": lower,
            "crossing_upper_grid_pct": upper,
            "first_grid_with_upper_pointwise_interval_at_target_pct": possible,
            "first_grid_with_lower_pointwise_interval_at_target_pct": conservative,
            "status": "crossing_bracketed" if upper is not None else "not_reached_in_grid",
            "monotone_curve": bool(np.all(np.diff(rates) >= -1e-12)),
            "interval_note": "Pointwise Monte Carlo intervals only; not a simultaneous confidence interval for the floor."}


def block_signs(design: Design, block_days: int, rng: np.random.Generator) -> np.ndarray:
    """Date-block wild multipliers, common across items, fixed observed-cell mask."""
    if block_days < 1:
        raise ValueError("block_days must be positive.")
    day_offsets = ((pd.DatetimeIndex(design.dates)-design.dates[0])/pd.Timedelta(days=1)).astype(int)
    offset = int(rng.integers(0,block_days))
    blocks = (np.asarray(day_offsets)+offset)//block_days
    signs = rng.choice(np.array([-1.,1.]), size=int(blocks.max())+1)
    return signs[blocks[design.tt]]


def bootstrap_log_outcome(design: Design, fit: dict, background: str, block_days: int,
                          rng: np.random.Generator) -> tuple[np.ndarray,float]:
    if background == "neutral_model":
        y = fit["null_fitted"]+fit["null_residual"]*block_signs(design, block_days, rng)
    elif background == "observed_model":
        y = fit["fitted"]+fit["residual"]*block_signs(design, block_days, rng)
    else:
        raise ValueError(background)
    clipped = float(np.mean(y<0))
    # Model on log(1+units). Respect nonnegative units; quantify truncation.
    return np.maximum(y,0), clipped


SCENARIOS = ("abrupt", "ramp7", "ramp21", "delay7", "delay14", "delay28",
             "distributed", "heterogeneous", "concentrated")


class Injection:
    """Allocate additions to existing candidate/post cells; never to missing cells.

    Definition of 100% scale: observed candidate pre-volume * nominal_post/nominal_pre.
    Pre-period item shares are fixed. Two documented exposure conventions are supported.
    """
    def __init__(self, design: Design, window: str):
        self.design = design
        self.pre_days, self.post_days = WINDOWS[window]
        self.d = design.d
        self.target = np.flatnonzero((design.treat == 1)&(design.post == 1))
        pre = self.d[(self.d.arm=="candidate")&(self.d.day<design.date)]
        amounts = pre.groupby("item", sort=True).units.sum()
        amounts = amounts[amounts>0]
        self.items = amounts.index.to_list()
        self.pre_total = float(amounts.sum())
        if not self.items or self.pre_total <= 0:
            raise ValueError("No positive candidate pre-volume for injection scale.")
        self.base = self.pre_total*self.post_days/self.pre_days
        self.share = amounts.to_numpy(float)/self.pre_total
        lookup = {v:i for i,v in enumerate(self.items)}
        targets = self.d.iloc[self.target]
        self.item_ix = targets.item.map(lookup).fillna(-1).to_numpy(int)
        self.offset = ((targets.day-design.date)/pd.Timedelta(days=1)).to_numpy(int)
        self.with_pre = self.item_ix >= 0

    def weights(self, scenario: str, rng: np.random.Generator, scale_mode: str="equal_intensity") -> tuple[np.ndarray,dict]:
        if scenario not in SCENARIOS:
            raise ValueError(scenario)
        n,t = len(self.items),self.post_days
        k = np.arange(t)[None,:]
        shape = np.ones((n,t))
        share = self.share.copy()
        if scenario.startswith("ramp"):
            r = int(scenario[4:])
            shape[:] = np.minimum((k+1)/r,1.)
        elif scenario.startswith("delay"):
            lag = int(scenario[5:])
            shape[:] = (k>=lag)
        elif scenario == "distributed":
            delay = rng.integers(0,8,size=n)[:,None]
            shape = (k>=delay)*rng.gamma(2.,.5,size=(n,t))
        elif scenario == "heterogeneous":
            delay = rng.integers(0,15,size=n)[:,None]
            ramp = rng.integers(1,22,size=n)[:,None]
            shape = np.clip((k-delay+1)/ramp,0.,1.)
        elif scenario == "concentrated":
            take = rng.choice(n, size=max(1,int(np.ceil(.1*n))), replace=False)
            selected = np.zeros(n,bool); selected[take] = True
            share[~selected] = 0
            share /= share.sum()
        full = share[:,None]*shape/t
        if scale_mode == "equal_total":
            if full.sum()>0:
                full /= full.sum()
        elif scale_mode != "equal_intensity":
            raise ValueError(scale_mode)
        w = np.zeros(len(self.target))
        good = self.with_pre
        w[good] = full[self.item_ix[good],self.offset[good]]
        planned = float(full.sum())
        observed = float(w.sum())
        return w, {"nominal_profile_fraction": planned, "observed_profile_fraction": observed,
                   "lost_to_unobserved_cells_fraction": planned-observed}

    def beta_path(self, y: np.ndarray, unit_weights: np.ndarray, grid_percent: np.ndarray) -> np.ndarray:
        """Exact full-estimator coefficient change via cached FWL weights."""
        base_beta = self.design.beta(y)
        amount = self.base*unit_weights
        ys = y[self.target]
        # log1p(u+a) - log1p(u) = log1p(a*exp(-y)); y=log1p(u).
        ratios = amount*np.exp(-ys)
        out = np.empty(len(grid_percent))
        cw = self.design.weights[self.target]
        for j, pct in enumerate(grid_percent):
            out[j] = base_beta+float(cw @ np.log1p(float(pct)/100.*ratios))
        return out
