"""Single source of truth for the §14 prohibition-scan gate.

§14 asks "是否触犯禁止行为清单？": ``answer=是`` means a prohibition was hit and
the trade must not go through.  Models routinely write ``answer=是`` to mean
"scan finished, nothing hit", so the reason text has to be cross-checked.

The previous cross-check was a bare substring test over the whole reason
(``any(p in reason for p in _DENIAL_PHRASES)``), which had two failure modes:

* false negative (dangerous): "未触发§14.1，但触发了追高禁止" contains 未触发,
  so a real violation was waved through into the order path;
* three copies of the word list drifted apart, in ``decision_nodes``,
  ``decision_tree`` and ``stage2_normalizer``.

This module parses the reason clause by clause instead.  An un-negated
violation verb anywhere wins; an explicit all-clear phrase or a negated
violation verb means "clean"; anything ambiguous counts as a violation,
because this is a safety gate — a false positive only costs a skipped trade,
while a false negative lets a forbidden order through.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Reasons are split into clauses so a denial in one clause cannot vouch for a
# violation asserted in another.
_CLAUSE_SPLIT_RE = re.compile(r"[。；;\n]+")

# Verbs that assert "this decision hits a prohibition".  The negative lookahead
# skips nominal uses ("触犯判定", "违规行为清单") that are not assertions.
_VIOLATION_VERB_RE = re.compile(
    r"(触犯|违反|违规|触发|命中)"
    r"(?![判定检核扫描清单项情况风险标准行为记录历史类型])"
)

# Tokens that, when they end the text right before a violation verb, negate it.
_NEGATION_PREFIXES = (
    "不存在",
    "不曾",
    "并无",
    "均未",
    "皆未",
    "全未",
    "尚未",
    "从未",
    "绝不",
    "没有",
    "未",
    "无",
    "没",
    "不",
    "非",
)

# Explicit "I looked and found nothing" phrasing, used when the reason contains
# no violation verb at all.
_STANDALONE_DENIALS = frozenset({"无", "否", "没有", "未", "均无", "皆无", "不存在", "none", "no", "clean"})

# Explicit "I looked and found nothing" phrasing.
_ALL_CLEAR_PHRASES = (
    "扫描通过",
    "通过扫描",
    "全部通过",
    "均通过",
    "未见异常",
    "无异常",
    "未发现异常",
    "检查通过",
    "核对通过",
    "no violation",
    "no violations",
    "not violated",
    "passed",
    "clean scan",
)


def _ends_with_negation(text: str) -> bool:
    """True when *text* ends with a negation token ("均未", "不存在", ...)."""
    return text.rstrip().endswith(_NEGATION_PREFIXES)


def _scan_reason(text: str) -> bool | None:
    """Return True (violation), False (clean) or None (ambiguous)."""
    affirmative = False
    negated = False
    for clause in _CLAUSE_SPLIT_RE.split(text):
        stripped = clause.strip()
        if not stripped:
            continue
        for sep in ("：", ":"):
            if sep in stripped:
                head, _, tail = stripped.partition(sep)
                if tail.strip().lower() in _STANDALONE_DENIALS:
                    # "触犯判定：无" — the verdict after the colon is the real answer.
                    negated = True
                    stripped = head.strip()
                    clause = stripped
                break
        if stripped.lower() in _STANDALONE_DENIALS:
            negated = True
            continue
        for match in _VIOLATION_VERB_RE.finditer(clause):
            before = clause[: match.start()]
            if _ends_with_negation(before):
                negated = True
            else:
                affirmative = True
    if affirmative:
        # "未触犯§14.1，但触发了追高禁止" lands here: the later clause wins.
        return True
    lowered = text.lower()
    if any(phrase in lowered for phrase in _ALL_CLEAR_PHRASES):
        return False
    if negated:
        return False
    return None


def section14_reason_denies_violation(reason: Any) -> bool:
    """True when the §14 *reason* text denies (rather than asserts) a hit.

    Ambiguous text returns False, i.e. it is treated as a real violation.
    """
    verdict = _scan_reason(str(reason or "").strip())
    return verdict is False


def section14_violated(trace: Any) -> bool:
    """True when *trace* holds a §14 node asserting a genuine violation.

    Only ``answer=是`` nodes can violate; a node whose reason text denies the
    hit overrides the answer (the model used the wrong answer value).
    """
    if not isinstance(trace, list):
        return False
    for item in trace:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id", "")).strip()
        if not node_id.startswith("14"):
            continue
        if str(item.get("answer", "")).strip() != "是":
            continue
        reason = item.get("reason", "")
        if section14_reason_denies_violation(reason):
            logger.debug(
                "§%s answer=是 but reason denies a hit; treating as NOT violated",
                node_id,
            )
            continue
        return True
    return False


def section14_has_genuine_violation(trace: Any) -> bool:
    """Alias kept for call sites that phrase it as a positive check."""
    return section14_violated(trace)