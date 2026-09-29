"""Relevance scoring. Rules live in config/rules.yaml (see the notes at its top)."""
import re

import yaml

from . import CONFIG_DIR


def _re(term):
    return re.compile(r"(?<![A-Za-z0-9])(?:" + term + r")(?![A-Za-z0-9])", re.I)


class Scorer:
    def __init__(self, rules=None):
        if rules is None:
            rules = yaml.safe_load((CONFIG_DIR / "rules.yaml").read_text(encoding="utf-8"))
        self.R = rules
        self.threshold = rules.get("threshold", 4)
        self.cats = [
            (name, bool(d.get("core")), [_re(t) for t in d.get("strong", [])], [_re(t) for t in d.get("medium", [])])
            for name, d in rules["categories"].items()
        ]
        self.weak = [_re(t) for t in rules.get("weak", [])]
        self.excl = [_re(t) for t in rules.get("exclude", [])]
        self.horg = [_re(t) for t in rules.get("health_orgs", [])]
        self.gen = [_re(t) for t in rules.get("generic_supply", [])]

    def score(self, title, org="", ttype=""):
        R = self.R
        text = f"{title} | {org or ''}"
        score, has_sm, has_strong, core = 0, False, False, False
        matched, cats, excluded = {}, {}, []
        for name, is_core, strong, medium in self.cats:
            for regs, w in ((strong, 3), (medium, 2)):
                for rx in regs:
                    m = rx.search(title)
                    if not m:
                        continue
                    k = m.group(0).lower()
                    if k in matched:
                        continue
                    matched[k] = w
                    score += w
                    has_sm = True
                    has_strong = has_strong or w == 3
                    cats[name] = cats.get(name, 0) + w
                    if is_core and (w == 3 or cats[name] >= 3):
                        core = True
        if org and any(rx.search(org) for rx in self.horg):
            for rx in self.gen:
                m = rx.search(title)
                if not m:
                    continue
                k = m.group(0).lower()
                has_sm = True
                if k not in matched:
                    matched[k] = 2
                    score += 2
                    c = "Pharmaceuticals & Medical Supplies"
                    cats[c] = cats.get(c, 0) + 2
                break
            if has_sm:
                score += R.get("health_org_bonus", 0)
        for rx in self.weak:
            m = rx.search(text)
            if m and m.group(0).lower() not in matched:
                matched[m.group(0).lower()] = 1
                score += 1
        pen = R.get("exclude_penalty", 4)
        for rx in self.excl:
            m = rx.search(title)
            if m:
                excluded.append(m.group(0).lower())
                score -= pen // 2 if has_strong else pen
        if re.match(r"^\s*(works?|civil)", ttype or "", re.I):
            score -= R.get("works_type_penalty", 2)
        relevant = has_sm and score >= self.threshold
        return {
            "score": score,
            "has_sm": has_sm,
            "relevant": relevant,
            "core": core and relevant,
            "categories": [c for c, _ in sorted(cats.items(), key=lambda x: -x[1])],
            "matched": list(matched),
            "excluded": excluded,
        }
