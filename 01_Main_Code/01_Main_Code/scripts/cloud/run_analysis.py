#!/usr/bin/env python3
"""Rebuild missing COSE calibration/injection code from a recovered daily panel.

This file is NEW CODE, not an authenticated historical implementation. It never
claims to reproduce an unknown historical seed or to manufacture missing results.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import logging
import platform
import sys
import traceback
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from cose_core import (VERSION, BAN, WINDOWS, SCENARIOS, Design, Injection, load_panel,
    subset_panel, event_window, window_audit, public_fit, save_json, sha256,
    bootstrap_log_outcome, wilson, floor_brackets)

LOG = logging.getLogger("cose")


def label_seed(seed: int, label: str) -> np.random.Generator:
    """Stable independent stream per named stage (not Python's process-randomized hash)."""
    import hashlib
    words = np.frombuffer(hashlib.sha256(label.encode()).digest()[:16], dtype="<u4").tolist()
    return np.random.default_rng(np.random.SeedSequence([seed, *words]))


def baseline(d: pd.DataFrame, out: Path, models: list[str]) -> list[dict]:
    output, audits, counts = [], [], []
    dates = [("actual", BAN), ("placebo_20170615",pd.Timestamp("2017-06-15",tz="UTC")),
             ("placebo_20180320",pd.Timestamp("2018-03-20",tz="UTC")),
             ("placebo_20180910",pd.Timestamp("2018-09-10",tz="UTC"))]
    for event_label,date in dates:
        for window in (list(WINDOWS) if event_label=="actual" else ["legacy21","tight21"]):
            audits.append(dict(event=event_label,**window_audit(d,date,window)))
            z = event_window(d,date,window)
            for model in models:
                try:
                    fit=Design(z,date,model).fit()
                    r=dict(event=event_label,event_date=str(date.date()),window=window,
                           status="computed_new_run",**public_fit(fit))
                    output.append(r)
                    LOG.info("baseline %s %s %s beta=%.8f se(item)=%.8f",event_label,window,model,
                             fit["coefficient"],fit["se_item"])
                except Exception as e:
                    output.append(dict(event=event_label,event_date=str(date.date()),window=window,
                                       model=model,status="failed",error=str(e)))
                    LOG.error("baseline failed %s %s %s: %s",event_label,window,model,e)
    pd.DataFrame(output).to_csv(out/"baseline_and_placebos.csv",index=False)
    save_json(out/"window_audit.json",audits)
    # Preserve input memberships and basic temporal counts, not a replacement classifier.
    x=d.groupby(["item","arm"],sort=True).agg(first_day=("day","min"),last_day=("day","max"),
                    observed_days=("day","size"),recorded_units=("units","sum")).reset_index()
    pre=d[d.day<BAN].groupby("item").agg(pre_days=("day","size"),pre_units=("units","sum"),
                                                    pre_median_units=("units","median"))
    x=x.merge(pre,on="item",how="left")
    x.to_csv(out/"input_membership_and_support.csv",index=False)
    # H1 descriptive rebuild: original month cutoff plus complete-month sensitivity.
    monthly=d[d.day<BAN].copy(); monthly["month"]=monthly.day.dt.strftime("%Y-%m")
    m=monthly.groupby(["month","arm"]).units.sum().unstack()
    h1={"historical_cutoff": "2018-10", "partial_month_note":
        "Historical final period includes October 2018 through partial October 2019 (13 month labels), not exactly 12 complete months."}
    if {"candidate","key"}.issubset(m.columns):
        m["key_per_100_candidate"]=100*m["key"]/m["candidate"].replace(0,np.nan)
        for name,mask in [("historical_baseline",m.index<"2018-10"),
                          ("historical_final_period",m.index>="2018-10"),
                          ("last_12_complete_months",(m.index>="2018-10")&(m.index<"2019-10"))]:
            v=m.loc[mask,"key_per_100_candidate"].dropna()
            h1[name]={"mean_monthly_key_per_100_candidate":float(v.mean()),"months":len(v)}
    m.to_csv(out/"h1_monthly_descriptive.csv")
    save_json(out/"h1_descriptive_summary.json",h1)
    # H3 legacy daily equal-item mean of within-item weighted-window prices.
    price="vwap" if "vwap" in d else ("price" if "price" in d else None)
    if price:
        t=d[["day","arm",price]].copy(); t[price]=pd.to_numeric(t[price],errors="coerce")
        means=t.groupby(["day","arm"])[price].mean().unstack()
        means.to_csv(out/"h3_daily_equal_item_means.csv")
        annual=means.groupby(means.index.year).mean()
        if {"candidate","key"}.issubset(annual.columns):
            annual["key_to_candidate_price_ratio"]=annual["key"]/annual["candidate"].replace(0,np.nan)
        annual.to_csv(out/"h3_annual_equal_item_means.csv")
        save_json(out/"h3_method.json",{"method":"Equal-item daily means, then equal-day annual means; membership from supplied panel.",
                  "source_price_column":price,"warning":"Window-median weighted prices are not exact transaction VWAP. Not the missing general-market index."})
    return output


def randomization(d: pd.DataFrame,out: Path,args: argparse.Namespace,model: str) -> tuple[pd.DataFrame,dict]:
    date_file=Path(args.date_file) if args.date_file else None
    if date_file:
        dates_frame=pd.read_csv(date_file)
        if "date" not in dates_frame:
            raise ValueError("Historical date CSV needs a date column.")
        dates=pd.to_datetime(dates_frame.date,utc=True,errors="raise")
        if dates.isna().any() or dates.duplicated().any() or not dates.equals(dates.dt.floor("D")):
            raise ValueError("Historical dates must be unique midnight UTC dates.")
        origin="user_supplied_date_list; original provenance must be checked separately"
    else:
        pre,post=WINDOWS[args.window]
        universe=pd.date_range(args.date_start,args.date_end,tz="UTC")
        # Coverage screening is mechanical. Detailed failed fits remain failed, not replaced.
        start=max(d.loc[d.arm==a,"day"].min() for a in ("candidate","control"))
        end=min(d.loc[d.arm==a,"day"].max() for a in ("candidate","control"))
        universe=universe[(universe-pd.Timedelta(days=pre)>=start)&
                          (universe+pd.Timedelta(days=post-1)<=end)]
        if len(universe)<args.draws:
            raise ValueError(f"Only {len(universe)} eligible historical dates for {args.draws} requested draws.")
        ix=label_seed(args.seed,"historical-date-list").choice(len(universe),size=args.draws,replace=False)
        dates=pd.Series(universe[ix])
        origin="newly_selected_dates; not recovered original seed/date list"
    hold=pd.Timestamp("2018-03-29",tz="UTC")
    pre,post=WINDOWS[args.window]; rows=[]
    for j,date in enumerate(dates):
        if j%25==0: LOG.info("%s historical date %d/%d",model,j+1,len(dates))
        z=event_window(d,date,args.window)
        row={"draw":j,"date":str(date.date()),"model":model,"window":args.window,
             "trade_hold_overlap":bool(date-pd.Timedelta(days=pre)<=hold<=date+pd.Timedelta(days=post-1))}
        try:
            row.update(public_fit(Design(z,date,model).fit())); row["status"]="computed_new_run"
        except Exception as e:
            row.update(status="failed",error=str(e)); LOG.warning("date %s failed: %s",date,e)
        rows.append(row)
    frame=pd.DataFrame(rows)
    frame.to_csv(out/f"historical_dates_{model}.csv",index=False)
    good=frame[frame.status=="computed_new_run"]
    actual=Design(event_window(d,BAN,args.window),BAN,model).fit()["coefficient"]
    summaries={}
    for name,part in (("all_draws",good),("excluding_trade_hold_overlap",good[~good.trade_hold_overlap])):
        if len(part)<20:
            summaries[name]={"n":len(part),"status":"insufficient_for_threshold"}; continue
        values=part.coefficient.to_numpy(float); mu=float(values.mean())
        summaries[name]={"n":len(values),"mean":mu,"sd_ddof1":float(values.std(ddof=1)),
           "threshold95":float(np.quantile(values,.95,method="linear")),
           "actual_coefficient":actual,"lower_tail_proportion":float(np.mean(values<=actual)),
           "upper_tail_proportion":float(np.mean(values>=actual)),
           "two_sided_about_zero_proportion":float(np.mean(np.abs(values)>=abs(actual))),
           "two_sided_about_mean_proportion":float(np.mean(np.abs(values-mu)>=abs(actual-mu)))}
    summary={"origin":origin,"seed":args.seed if not date_file else None,
             "date_file_sha256":sha256(date_file) if date_file else None,
             "date_bounds":[args.date_start,args.date_end],"draws_requested":len(dates),
             "failed_draws":len(frame)-len(good),"window":args.window,"model":model,
             "membership":"Fixed from supplied panel, including retrospectively selected 2019 membership; not prospective historical selection.",
             "interpretation":"Historical reference distribution, not randomized-treatment causal inference. Windows overlap; no IID historical confidence intervals asserted.",
             "summaries":summaries}
    save_json(out/f"historical_summary_{model}.json",summary)
    return frame,summary


def injection(d: pd.DataFrame,out: Path,args: argparse.Namespace,model: str,history: dict) -> None:
    z=event_window(d,BAN,args.window); design=Design(z,BAN,model); fit=design.fit(); inj=Injection(design,args.window)
    root_label=f"{model}/{args.window}/{args.scale_mode}/block{args.block_days}"
    # Independent calibration bank for a new conditional wild-null threshold.
    calrng=label_seed(args.seed,root_label+"/null-calibration")
    null_coef=[]; trunc=[]
    for b in range(args.calibration_reps):
        y,c=bootstrap_log_outcome(design,fit,"neutral_model",args.block_days,calrng)
        null_coef.append(design.beta(y)); trunc.append(c)
    null_coef=np.asarray(null_coef)
    wildq=float(np.quantile(null_coef,.95,method="linear"))
    thresholds={"conditional_wild_null95":wildq}
    if history.get("failed_draws",0)==0:
        h=history["summaries"].get("all_draws",{})
        if "threshold95" in h: thresholds["historical95"]=h["threshold95"]
    else:
        LOG.warning("Omitting historical threshold from injections because at least one selected historical fit failed.")
    clean=history["summaries"].get("excluding_trade_hold_overlap",{})
    if "threshold95" in clean and history.get("failed_draws",0)==0:
        thresholds["historical95_excluding_trade_hold"]=clean["threshold95"]
    pd.DataFrame({"rep":np.arange(args.calibration_reps),"coefficient":null_coef,
                  "clipped_fraction":trunc}).to_csv(out/f"injection_null_calibration_{model}.csv",index=False)
    # Quantile Monte Carlo uncertainty conditional on this independent simulation bank.
    qrng=label_seed(args.seed,root_label+"/quantile-mc")
    quantiles=[np.quantile(qrng.choice(null_coef,size=len(null_coef),replace=True),.95,method="linear")
               for _ in range(args.quantile_bootstrap)]
    calibration={"model":model,"window":args.window,"seed":args.seed,
        "thresholds":thresholds,"calibration_reps":args.calibration_reps,
        "null_coef_mean":float(null_coef.mean()),"mean_clipped_fraction":float(np.mean(trunc)),
        "wild_threshold_mc_interval":np.quantile(quantiles,[.025,.975]).tolist(),
        "uncertainty_scope":"Conditional calibration-bank Monte Carlo uncertainty only; not raw-data/source uncertainty.",
        "background":"Date-block wild residual draws on log(1+units), truncated at zero; fixed observed cells. Newly chosen revision-stage model.",
        "neutral_definition":"Restricted nuisance fit without candidate*post; residuals include omitted effect; truncation can induce bias; zero-dose diagnostics are mandatory.",
        "observed_definition":"Unrestricted fitted nuisance+effect plus block-wild full-model residuals; not literal repeated observation of the original market.",
        "block_days":args.block_days,"scale_mode":args.scale_mode,"candidate_pre_units":inj.pre_total,
        "100_percent_nominal_units":inj.base,"frozen_coefficient":fit["coefficient"]}
    save_json(out/f"injection_calibration_{model}.json",calibration)
    summary_rows=[]; floor_rows=[]; run_rows=[]
    for background in ("neutral_model","observed_model"):
        for scenario in args.scenarios:
            LOG.info("injection %s %s %s, %d reps",model,background,scenario,args.reps)
            # Common background random numbers across scenarios, independent of calibration.
            brng=label_seed(args.seed,root_label+"/evaluation/"+background)
            srng=label_seed(args.seed,root_label+"/shape/"+scenario)
            paths=np.empty((args.reps,len(args.grid)))
            profile=[]; observed=[]; clipped=[]
            for b in range(args.reps):
                y,c=bootstrap_log_outcome(design,fit,background,args.block_days,brng)
                w,detail=inj.weights(scenario,srng,args.scale_mode)
                paths[b]=inj.beta_path(y,w,args.grid)
                profile.append(detail["nominal_profile_fraction"])
                observed.append(detail["observed_profile_fraction"])
                clipped.append(c)
            save_json(out/f"injection_detail_{model}_{background}_{scenario}.json",{
                "mean_nominal_profile_fraction":float(np.mean(profile)),
                "mean_observed_profile_fraction":float(np.mean(observed)),
                "mean_clipped_fraction":float(np.mean(clipped)),
                "warning":"100% scale is pre-period-equivalent volume. Delays/ramps may deliver less within-window signal in equal_intensity mode; missing cells receive no injected units."})
            # Store every simulated coefficient, not a fabricated recovery summary.
            detail_frame=pd.DataFrame(paths,columns=[f"pct_{v:g}" for v in args.grid])
            detail_frame.insert(0,"rep",np.arange(args.reps))
            detail_frame.to_csv(out/f"injection_coefficients_{model}_{background}_{scenario}.csv.gz",index=False,compression="gzip")
            for threshold_name,q in thresholds.items():
                rates=[]; lowers=[]; uppers=[]
                for j,g in enumerate(args.grid):
                    hit=int((paths[:,j]>q).sum()); p=hit/args.reps; lo,hi=wilson(hit,args.reps)
                    rates.append(p); lowers.append(lo); uppers.append(hi)
                    summary_rows.append({"model":model,"window":args.window,"background":background,
                        "scenario":scenario,"scale_mode":args.scale_mode,"threshold_source":threshold_name,
                        "threshold":q,"injection_percent":g,"reps":args.reps,"recovered":hit,
                        "recovery_rate":p,"mcse_conditional":float(np.sqrt(p*(1-p)/args.reps)),
                        "mc_interval_lower":lo,"mc_interval_upper":hi,
                        "mean_planned_added_units":g/100*inj.base*float(np.mean(profile)),
                        "mean_observed_added_units":g/100*inj.base*float(np.mean(observed)),
                        "mean_clipped_log_fraction":float(np.mean(clipped)),
                        "result_status":"revision_model_simulation; not authenticated historical recovery"})
                floor_rows.append({"model":model,"window":args.window,"background":background,
                    "scenario":scenario,"scale_mode":args.scale_mode,"threshold_source":threshold_name,
                    **floor_brackets(np.asarray(args.grid),np.asarray(rates),np.asarray(lowers),np.asarray(uppers))})
            # Checkpoint after each scenario; a stopped run retains finished results.
            pd.DataFrame(summary_rows).to_csv(out/f"recovery_curves_{model}.csv",index=False)
            pd.DataFrame(floor_rows).to_csv(out/f"floor_brackets_{model}.csv",index=False)
    # Scale comparison is observed turnover, not measured laundering flow.
    pre_days,_=WINDOWS[args.window]
    pre=d[d.day.between(BAN-pd.Timedelta(days=pre_days),BAN-pd.Timedelta(days=1))]
    totals=pre.groupby("arm").units.sum()
    save_json(out/f"recorded_key_scale_{model}.json",{
      "key_units":float(totals.get("key",0)),"candidate_units":float(totals.get("candidate",0)),
      "key_share_percent":float(100*totals["key"]/totals["candidate"]) if "key" in totals and totals.get("candidate",0)>0 else None,
      "status":"computed from supplied panel; key arm absent is not evidence of zero keys" if "key" not in totals else "computed recorded turnover ratio",
      "interpretation":"Unit-turnover comparison, not illicit share, unique key stock, fiat value, or direct value conservation."})


def parse_args() -> argparse.Namespace:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path,help="New empty output directory; never overwrites a prior run.")
    p.add_argument("--stage",choices=["baseline","randomization","injection","all"],default="baseline")
    p.add_argument("--models",nargs="+",choices=["item_post","twfe"],default=["item_post","twfe"])
    p.add_argument("--window",choices=list(WINDOWS),default="legacy21")
    p.add_argument("--date-file",default=None)
    p.add_argument("--date-start",default="2017-03-01")
    p.add_argument("--date-end",default="2019-08-31")
    p.add_argument("--draws",type=int,default=150)
    p.add_argument("--seed",type=int,default=20261112,help="New revision seed; NOT the unlocated historical seed.")
    p.add_argument("--reps",type=int,default=2500)
    p.add_argument("--calibration-reps",type=int,default=2500)
    p.add_argument("--quantile-bootstrap",type=int,default=1000)
    p.add_argument("--block-days",type=int,default=7)
    p.add_argument("--scale-mode",choices=["equal_intensity","equal_total"],default="equal_intensity")
    p.add_argument("--scenarios",nargs="+",choices=SCENARIOS,default=list(SCENARIOS))
    p.add_argument("--grid",nargs="+",type=float,default=[0,1,3,5,10,20,30,44,60,80,100])
    p.add_argument("--exclude-items",type=Path,help="Verified container CSV with unique item column. No regex guessing.")
    a=p.parse_args()
    if any(x<1 for x in (a.draws,a.reps,a.calibration_reps,a.quantile_bootstrap,a.block_days)):
        p.error("Counts and block length must be positive.")
    if not a.grid or a.grid[0]!=0 or any(not np.isfinite(x) or x<0 for x in a.grid) or list(a.grid)!=sorted(set(a.grid)):
        p.error("Grid must be unique, ascending, finite, nonnegative and start at zero.")
    if a.out.exists() and any(a.out.iterdir()): p.error("Output directory is not empty; use a new run directory.")
    return a


def main() -> int:
    args=parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",
             handlers=[logging.FileHandler(args.out/"execution.log",encoding="utf-8"),logging.StreamHandler()])
    started=datetime.now(timezone.utc).isoformat()
    save_json(args.out/"run_configuration.json",{**vars(args),"version":VERSION,"start_utc":started,
                "status":"new reconstruction/revision, not recovered historical execution",
                "python":sys.version,"platform":platform.platform(),"numpy":np.__version__,
                "pandas":pd.__version__,"scipy":scipy.__version__,
                "code_hashes":{p.name:sha256(p) for p in Path(__file__).parent.glob("*.py")}})
    try:
        d,manifest=load_panel(args.panel); d,sub=subset_panel(d,args.exclude_items)
        save_json(args.out/"panel_audit.json",{**manifest,**sub})
        LOG.info("Loaded %d daily rows; %d items",len(d),d.item.nunique())
        subfit_failures=0
        if args.stage in ("baseline","all"):
            results=baseline(d,args.out,args.models)
            subfit_failures+=sum(r.get("status")=="failed" for r in results)
        if args.stage in ("randomization","injection","all"):
            for model in args.models:
                _,summary=randomization(d,args.out,args,model)
                subfit_failures+=int(summary.get("failed_draws",0))
                if args.stage in ("injection","all"):
                    injection(d,args.out,args,model,summary)
        save_json(args.out/"RUN_STATUS.json",{"status":"completed" if subfit_failures==0 else "completed_with_failed_fits", "failed_subfits":subfit_failures, "start_utc":started,
                 "end_utc":datetime.now(timezone.utc).isoformat(),
                 "scope":"Code execution complete; analyst review of diagnostics and failed subfits still required."})
        save_json(args.out/"OUTPUT_SHA256.json",{str(p.relative_to(args.out)):sha256(p)
              for p in args.out.rglob("*") if p.is_file() and p.name not in {"execution.log","OUTPUT_SHA256.json"}})
        return 0
    except Exception as e:
        LOG.exception("Run failed")
        save_json(args.out/"RUN_STATUS.json",{"status":"failed","error":str(e),"start_utc":started,
                          "end_utc":datetime.now(timezone.utc).isoformat()})
        return 1

if __name__=="__main__":
    raise SystemExit(main())
