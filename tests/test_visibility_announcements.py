from __future__ import annotations

from engine.visibility import Visibility


def test_incident_occurred_announcement_uses_occurrence_phrase() -> None:
    text = Visibility.create_announcement(
        "incident_occurred",
        {"incident_id": "murder", "day": 2},
    )

    assert text == "第 2 天，谋杀事件发生了"


def test_incident_phenomenon_announcement_reports_no_phenomenon() -> None:
    text = Visibility.create_announcement(
        "incident_phenomenon",
        {"incident_id": "murder", "day": 2, "has_phenomenon": False},
    )

    assert text == "第 2 天，谋杀无现象"


def test_incident_phenomenon_announcement_skips_positive_placeholder() -> None:
    text = Visibility.create_announcement(
        "incident_phenomenon",
        {"incident_id": "murder", "day": 2, "has_phenomenon": True},
    )

    assert text == ""
