"""
config.py - project-wide settings for the demo dataset. Imported first by the run scripts.

The Kaggle resumes were written years ago, so "Current" in a job is counted up to this date
instead of today. Your own PowerShell setting (SYNAPSEHR_AS_OF) still wins if you set one.
For live applicants, delete the line below: then today's date is used.
"""
import os

os.environ.setdefault("SYNAPSEHR_AS_OF", "2018-12-31")
