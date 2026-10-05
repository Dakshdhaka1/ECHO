"""News headline -> event type (M2 rule baseline, Kind = Rule).

The ML event classifier in ML_PIPELINE §4 needs a hand-labelled headline set; until that exists the
dashboard uses these documented keyword rules and labels them as Rule. Each rule needs the company
to be named in the headline (enforced by the news source), so generic market news is excluded.
"""

from __future__ import annotations

import re

RULES = [
    ("BANKRUPTCY_NEWS", "Bankruptcy reported in the news", 0, "HIGH",
     r"\b(chapter 11|files? for bankruptcy|bankruptcy (filing|protection)|insolven\w*|receivership)\b"),
    ("LAYOFFS", "Layoffs reported", 0, "MEDIUM",
     r"\b(lay(s|ing)? off|layoffs?|job cuts?|cuts? \d[\d,]* jobs|workforce reduction|redundanc\w+|furlough\w*)\b"),
    ("LEGAL_REGULATORY", "Lawsuit or regulatory action reported", 10, "MEDIUM",
     r"\b(su(es|ed|ing)|lawsuit|class action|antitrust|probe|investigat\w+|fined?|penalt\w+|settle\w*|"
     r"subpoena|indict\w*|sec charges|doj|ftc|recall\w*)\b"),
    ("CYBER_INCIDENT", "Cyber incident reported", 15, "MEDIUM",
     r"\b(data breach|hack(ed|ers?)|cyber ?attack|ransomware|outage)\b"),
    ("LEADERSHIP_CHANGE", "Leadership change reported", 0, "LOW",
     r"\b(ceo|cfo|chief executive|chief financial).{0,40}\b(resign\w*|steps? down|ousted|fired|departs?|exit\w*|replac\w+)\b"),
    ("M_AND_A", "Merger or acquisition reported", 0, "LOW", r"\b(acquir\w+|acquisition|merger|takeover|buyout)\b"),
    ("EARNINGS", "Earnings reported", 0, "LOW", r"\b(earnings|quarterly results|revenue (beat|miss)|guidance|eps)\b"),
]
_COMPILED = [(t, label, pen, sev, re.compile(rx, re.I)) for t, label, pen, sev, rx in RULES]


def classify(title: str) -> tuple[str, str, float, str] | None:
    """First matching rule (rules are ordered from most to least severe)."""
    for event_type, label, penalty, severity, rx in _COMPILED:
        if rx.search(title):
            return event_type, label, penalty, severity
    return None
