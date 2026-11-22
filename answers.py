"""
answers.py - turn an answer with "[source: file.md > Section]" tags into plain text plus a list of readable sources,
so no screen ever has to show a tag or a file name.
"""
import re

TAG = re.compile(r"\s*\[source:\s*([^\]]+?)\s*\]")


def source_label(source):
    """'remote_work_policy.md > Eligibility' -> 'Remote work policy, Eligibility'; 'Your leave record' stays as is."""
    document, _, section = source.partition(">")
    name = re.sub(r"\.md$", "", document.strip(), flags=re.I).replace("_", " ").replace("-", " ")
    name = name[:1].upper() + name[1:]
    return f"{name}, {section.strip()}" if section.strip() else name


def split_answer(text):
    """Return (plain text, [readable sources])."""
    sources = []
    body = TAG.sub(lambda m: sources.append(source_label(m.group(1))) or "", text or "").strip()
    return body, sources
