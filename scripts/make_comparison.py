"""Write comparisons/<A>_<B>.json linking Report A and Report B with measured metrics.

    python scripts/make_comparison.py --report-a PATH --report-b PATH --demo-repo PATH
        [--leaky-sweep ID --grouped-sweep ID]

Every number is read from files: the two validity-report.json files and the sweep
summaries committed in the demo repo (run_artifacts/sweeps/*.json). Nothing is typed by hand.
Without explicit sweep IDs it uses the newest sweep whose overlaps are all > 0 (leaky) and the
newest completed sweep whose overlaps are all 0 (grouped), both under Python 3.12.
Neither report is modified; an existing comparison file is never overwritten.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def report_summary(path: Path) -> dict:
    r = load(path)
    b, c = r["binding"], r["checks"]
    return {
        "report_path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(),
        "run_id": r["run_id"],
        "status": r["status"],
        "head_sha": b["head_sha"],
        "base_sha": b["base_sha"],
        "analyzer_commit": b["analyzer_commit"],
        "overlap_count": (c["verify_split_overlap"].get("result") or {}).get("overlap_count"),
        "checks": {k: {"contribution": v["contribution"], "summary": v["summary"]} for k, v in c.items()},
        "history_confirmed_affected": r["history"]["confirmed_count"],
    }


def pick_sweep(sweeps: list[dict], leaky: bool) -> dict | None:
    def ok(s):
        ov = s.get("overlap_count") or []
        py = str((s.get("dependency_versions") or {}).get("python", ""))
        if not ov or None in ov or not py.startswith("3.12"):
            return False
        return all(v > 0 for v in ov) if leaky else all(v == 0 for v in ov)
    cands = [s for s in sweeps if ok(s)]
    return sorted(cands, key=lambda s: s["sweep_id"])[-1] if cands else None


def sweep_summary(s: dict) -> dict:
    pa = s["patient_auc"]
    return {
        "sweep_id": s["sweep_id"],
        "split_function": s["split_function"],
        "code_git_sha": s["git_sha"],
        "python": s["dependency_versions"].get("python"),
        "seeds": s["seeds"],
        "run_ids": s.get("run_ids") or [r["run_id"] for r in s.get("runs", [])],
        "overlap_count": s["overlap_count"],
        "patient_auc": pa["values"],
        "patient_auc_mean": pa["mean"],
        "patient_auc_population_std": pa["population_std"],
        "defined": f"{pa['defined']}/{pa['total']}",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report-a", type=Path, required=True)
    ap.add_argument("--report-b", type=Path, required=True)
    ap.add_argument("--demo-repo", type=Path, required=True)
    ap.add_argument("--leaky-sweep")
    ap.add_argument("--grouped-sweep")
    args = ap.parse_args()

    a, b = report_summary(args.report_a.resolve()), report_summary(args.report_b.resolve())
    if a["status"] != "blocked" or b["status"] != "no_findings":
        sys.exit(f"ERROR: expected A=blocked and B=no_findings, got {a['status']} / {b['status']}")

    sweeps = [load(p) for p in sorted((args.demo_repo / "run_artifacts" / "sweeps").glob("*.json"))]
    by_id = {s["sweep_id"]: s for s in sweeps}
    leaky = by_id.get(args.leaky_sweep) if args.leaky_sweep else pick_sweep(sweeps, leaky=True)
    grouped = by_id.get(args.grouped_sweep) if args.grouped_sweep else pick_sweep(sweeps, leaky=False)
    if leaky is None or grouped is None:
        sys.exit("ERROR: could not find both a leaky and a grouped sweep; pass --leaky-sweep/--grouped-sweep")

    ls, gs = sweep_summary(leaky), sweep_summary(grouped)
    diffs = [x - y for x, y in zip(ls["patient_auc"], gs["patient_auc"]) if x is not None and y is not None]
    comparison = {
        "comparison_id": f"{a['run_id'][:8]}_{b['run_id'][:8]}",
        "report_a": a,
        "report_b": b,
        "patient_overlap": {"report_a": a["overlap_count"], "report_b": b["overlap_count"]},
        "auc": {
            "note": ("Patient-level ROC AUC from committed training sweeps. The leaky sweep uses the "
                     "row-level split; the grouped sweep uses the patient-grouped split. The two splits hold "
                     "out different patients, so the difference describes this synthetic benchmark only."),
            "leaky": ls,
            "grouped": gs,
            "per_seed_difference_leaky_minus_grouped": diffs,
            "mean_difference": sum(diffs) / len(diffs) if diffs else None,
        },
    }
    out_dir = ROOT / "comparisons"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{comparison['comparison_id']}.json"
    with open(out, "x", encoding="utf-8", newline="\n") as f:
        json.dump(comparison, f, indent=2)
        f.write("\n")
    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"  overlap {a['overlap_count']} -> {b['overlap_count']}; "
          f"AUC seed {ls['seeds'][0]}: {ls['patient_auc'][0]} -> {gs['patient_auc'][0]}; "
          f"mean {ls['patient_auc_mean']:.4f} -> {gs['patient_auc_mean']:.4f}")


if __name__ == "__main__":
    main()