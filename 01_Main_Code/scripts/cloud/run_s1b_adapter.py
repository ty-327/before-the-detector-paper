#!/usr/bin/env python3
"""Run recovered S1b statistical logic with isolated input/output paths.

Only the input folder and two output paths are changed in a written execution copy.
No statistical logic is repaired here. Legacy denominator, missingness, category and
follow-up limitations remain visible. Never overwrite an original s1b_results.txt.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import difflib
from pathlib import Path
import subprocess
import sys
from cose_core import save_json, sha256


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path,help="Folder directly containing item CSV histories, not a ZIP or daily panel.")
    p.add_argument("--out",required=True,type=Path,help="New, empty, separate output directory.")
    p.add_argument("--source",type=Path,default=Path(__file__).resolve().parents[1]/"recovered"/"s1b_analysis.py")
    a=p.parse_args(); a.input=a.input.resolve(); a.out=a.out.resolve(); a.source=a.source.resolve()
    if not a.input.is_dir(): p.error("Input is not a directory.")
    if not any(a.input.glob("*.csv")): p.error("No item CSVs directly in input directory.")
    if a.out==a.input or a.input in a.out.parents: p.error("Use an output directory outside the raw CSV folder.")
    if a.out.exists() and any(a.out.iterdir()): p.error("Output is not empty. Use a new run folder.")
    text=a.source.read_text(encoding="utf-8")
    replacements={
       'HERE = os.path.dirname(os.path.abspath(__file__))':f'HERE = {str(a.input)!r}',
       'os.path.join(HERE, "s1b_spikes.csv")':repr(str(a.out/"s1b_spikes.csv")),
       'os.path.join(HERE, "s1b_results.txt")':repr(str(a.out/"s1b_results.txt")),
    }
    adapted=text
    for old,new in replacements.items():
        if adapted.count(old)!=1: p.error(f"Source changed: expected exactly one {old!r}. Inspect source before adapting.")
        adapted=adapted.replace(old,new)
    compile(adapted,str(a.out/"executed_s1b_io_adapter.py"),"exec")
    a.out.mkdir(parents=True,exist_ok=True)
    script=a.out/"executed_s1b_io_adapter.py"; script.write_text(adapted,encoding="utf-8")
    (a.out/"io_only_changes.patch").write_text("".join(difflib.unified_diff(text.splitlines(True),adapted.splitlines(True),
                                    fromfile=a.source.name,tofile=script.name)),encoding="utf-8")
    metadata={"created_utc":datetime.now(timezone.utc).isoformat(),"source_name":a.source.name,
              "source_sha256":sha256(a.source),"executed_sha256":sha256(script),
              "status":"new execution of recovered statistical logic, with three documented I/O substitutions",
              "warning":"Not recovered historical output. Legacy statistical/data-handling limitations remain; review before manuscript use."}
    save_json(a.out/"s1b_adapter_provenance.json",metadata)
    with (a.out/"s1b_execution.log").open("w",encoding="utf-8") as log:
        done=subprocess.run([sys.executable,str(script)],input="\n"*8,text=True,stdout=log,stderr=subprocess.STDOUT,check=False)
    logtext=(a.out/"s1b_execution.log").read_text(encoding="utf-8",errors="replace")
    paths=[a.out/"s1b_results.txt",a.out/"s1b_spikes.csv"]
    ok=done.returncode==0 and all(x.is_file() for x in paths) and "Traceback (most recent call last)" not in logtext
    save_json(a.out/"RUN_STATUS.json",{"status":"completed_new_run" if ok else "failed", "returncode":done.returncode,
            "outputs":{x.name:sha256(x) for x in paths if x.is_file()},"end_utc":datetime.now(timezone.utc).isoformat()})
    print(logtext)
    return 0 if ok else 1

if __name__=="__main__": raise SystemExit(main())
