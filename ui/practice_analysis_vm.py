"""Pure view-model for the Practice Analysis surface (Qt-free).

UAT Finding 2 requires the output to be structured — session summary, a
per-corner pattern table, repeatable issues, strong corners, isolated events,
driver-feedback agreement and targeted next tests — NOT one large plain-text
box. This module turns a ``PracticeAnalysisReport`` into the rows/lines the Qt
tab renders into tables and lists, so the presentation is testable without Qt.
"""
from __future__ import annotations

from typing import List, Tuple

from strategy.practice_pattern_analysis import (
    PracticeAnalysisReport, CornerPatternFinding, RecurrenceClass,
    FeedbackAgreement, Trend,
)


CORNER_TABLE_COLUMNS: Tuple[str, ...] = (
    "Corner", "Phase", "Finding", "Laps", "Recur %", "Pattern",
    "Trend", "Conf.", "Feedback", "Author?",
)


_CLASS_LABEL = {
    RecurrenceClass.STRONGLY_RECURRING: "Strongly recurring",
    RecurrenceClass.RECURRING: "Recurring",
    RecurrenceClass.EMERGING: "Emerging",
    RecurrenceClass.ISOLATED: "Isolated",
    RecurrenceClass.EXCLUDED: "Excluded",
    RecurrenceClass.STRENGTH: "Strength",
}

_FEEDBACK_LABEL = {
    FeedbackAgreement.AGREES: "Agrees",
    FeedbackAgreement.CONTRADICTS: "Contradicts",
    FeedbackAgreement.NONE: "—",
}

_TREND_LABEL = {
    Trend.IMPROVING: "Improving",
    Trend.WORSENING: "Worsening",
    Trend.STABLE: "Stable",
    Trend.UNKNOWN: "—",
}


def session_summary_rows(report: PracticeAnalysisReport) -> List[Tuple[str, str]]:
    return [
        ("Total laps", str(report.total_laps)),
        ("Clean laps analysed", str(report.clean_laps)),
        ("Corners analysed", str(report.corners_analysed)),
        ("Repeatable issues", str(len(report.repeatable_issues))),
        ("Strong corners", str(len(report.strong_corners))),
        ("Isolated events", str(len(report.isolated_events))),
    ]


def _corner_cell(f: CornerPatternFinding) -> str:
    return f.corner_name if f.location_resolved else "Unresolved"


def corner_table_rows(report: PracticeAnalysisReport) -> List[List[str]]:
    rows: List[List[str]] = []
    for f in report.findings:
        rows.append([
            _corner_cell(f),
            f.phase,
            f.finding,
            f"{f.laps_affected}/{f.clean_laps_observed}",
            f"{f.recurrence_pct:.0f}%",
            _CLASS_LABEL.get(f.recurrence_class, f.recurrence_class.value),
            _TREND_LABEL.get(f.trend, "—"),
            f.confidence.title(),
            _FEEDBACK_LABEL.get(f.driver_feedback_agreement, "—"),
            "Yes" if f.setup_authoring_eligible else "No",
        ])
    return rows


def repeatable_lines(report: PracticeAnalysisReport) -> List[str]:
    return [f.headline() for f in report.repeatable_issues]


def strong_lines(report: PracticeAnalysisReport) -> List[str]:
    return [s.note for s in report.strong_corners]


def isolated_lines(report: PracticeAnalysisReport) -> List[str]:
    out = []
    for f in report.isolated_events:
        suffix = ""
        if f.recurrence_class is RecurrenceClass.EXCLUDED:
            suffix = " (excluded from setup authoring)"
        out.append(f.headline() + suffix)
    return out


def feedback_lines(report: PracticeAnalysisReport) -> List[str]:
    out = []
    for f in report.findings:
        if f.driver_feedback_agreement is FeedbackAgreement.AGREES:
            out.append(f"Telemetry agrees with your feedback: {f.headline()}")
        elif f.driver_feedback_agreement is FeedbackAgreement.CONTRADICTS:
            out.append(
                f"Telemetry contradicts your feedback at {_corner_cell(f)} "
                f"({f.phase}) — measured {f.finding}.")
    return out


def targeted_test_lines(report: PracticeAnalysisReport) -> List[str]:
    return list(report.targeted_tests)


def empty_state(report: PracticeAnalysisReport) -> str:
    if report.clean_laps <= 0:
        return ("No clean laps captured yet. Drive clean laps (no offs, no pit "
                "in/out) so patterns can be analysed across laps.")
    if not report.findings and not report.strong_corners:
        return (f"Analysed {report.clean_laps} clean lap(s): no repeated issues "
                "and not enough corner coverage yet to highlight strengths.")
    return ""
