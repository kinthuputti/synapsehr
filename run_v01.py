"""
run_v01.py - SynapseHR v0.1: reader -> scorer -> human checkpoint (resume screening only).

    python run_v01.py                 # job 1, you approve/reject each candidate
    python run_v01.py --job 2 --n 5   # nurse job, 5 same-profession resumes + 2 others
    python run_v01.py --auto          # no prompts (for quick testing only)
    python run_v01.py --reader llm    # use Gemini to read resumes (needs GEMINI_API_KEY / GEMINI_MODEL)

Needs data/sample/resume_sample.csv (made by sample_resumes.py).
"""
import argparse

import config  # noqa: F401  (reference date for the old Kaggle resumes)
from screening import screen

parser = argparse.ArgumentParser()
parser.add_argument("--job", type=int, default=1, help="job_id from jobs.py")
parser.add_argument("--n", type=int, default=5, help="resumes from the matching profession")
parser.add_argument("--others", type=int, default=2, help="resumes from other professions (bad fits)")
parser.add_argument("--auto", action="store_true", help="skip the human prompts (testing only)")
parser.add_argument("--reader", choices=["rule", "llm"], default="rule",
                    help="rule = keyword rules (no key needed), llm = Gemini (needs API key)")
args = parser.parse_args()

entries = screen(args.job, args.n, args.others, args.reader, args.auto)

print("\n" + "=" * 64)
print(f"Done. {len(entries)} decisions logged to audit/audit_log.jsonl")
print(f"  shortlist: {sum(e['final_decision'] == 'shortlist' for e in entries)}"
      f"   review: {sum(e['final_decision'] == 'review' for e in entries)}"
      f"   reject: {sum(e['final_decision'] == 'reject' for e in entries)}")
print(f"  human overrides: {sum(e['overridden'] for e in entries)}"
      f"   flagged for a check: {sum(e['flagged_for_check'] for e in entries)}")
