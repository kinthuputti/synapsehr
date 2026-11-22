"""
jobs.py - fake job postings, one per profession in the Kaggle sample.
must_have  : a candidate missing these is a weak fit
nice_to_have: bonus points
Edit these freely: changing the requirements is part of testing and tweaking.
"""
JOBS = [
    {"job_id": 1, "title": "Software Engineer", "category": "INFORMATION-TECHNOLOGY", "min_years": 2,
     "must_have": ["python", "sql", "git"],
     "nice_to_have": ["java", "aws", "docker", "linux", "agile"]},
    {"job_id": 2, "title": "Registered Nurse", "category": "HEALTHCARE", "min_years": 2,
     "must_have": ["patient care", "cpr", "medication"],
     "nice_to_have": ["emr", "triage", "icu", "charting", "infection control"]},
    {"job_id": 3, "title": "HR Generalist", "category": "HR", "min_years": 2,
     "must_have": ["recruiting", "onboarding", "employee relations"],
     "nice_to_have": ["payroll", "benefits", "hris", "training and development", "compliance"]},
    {"job_id": 4, "title": "Construction Project Manager", "category": "CONSTRUCTION", "min_years": 5,
     "must_have": ["project management", "budget", "safety"],
     "nice_to_have": ["osha", "scheduling", "contracts", "autocad", "subcontractor"]},
    {"job_id": 5, "title": "Financial Analyst", "category": "FINANCE", "min_years": 2,
     "must_have": ["financial analysis", "excel", "budget"],
     "nice_to_have": ["forecasting", "modeling", "gaap", "reporting", "variance"]},
    {"job_id": 6, "title": "Classroom Teacher", "category": "TEACHER", "min_years": 2,
     "must_have": ["lesson plans", "classroom management", "curriculum"],
     "nice_to_have": ["assessment", "differentiated instruction", "parent communication", "iep", "educational technology"]},
]


def get_job(job_id):
    return next(j for j in JOBS if j["job_id"] == job_id)


def all_terms():
    """Every skill term mentioned by any job. The reader looks for these."""
    return sorted({t for j in JOBS for t in j["must_have"] + j["nice_to_have"]})
