from __future__ import annotations

from dataclasses import dataclass, field

from engine.models.incident import IncidentSchedule
from engine.models.script import CharacterSetup


@dataclass(frozen=True)
class CharacterDraft:
    character_id: str
    identity_id: str
    initial_area_id: str = ""
    territory_area_id: str = ""
    entry_loop: int = 0
    entry_day: int = 0


@dataclass(frozen=True)
class IncidentDraft:
    incident_id: str
    day: int
    perpetrator_id: str


@dataclass(frozen=True)
class NewGameDraft:
    module_id: str
    loop_count: int
    days_per_loop: int
    rule_y_id: str
    rule_x_ids: list[str] = field(default_factory=list)
    characters: list[CharacterDraft] = field(default_factory=list)
    incidents: list[IncidentDraft] = field(default_factory=list)


def default_phase5_draft() -> NewGameDraft:
    return NewGameDraft(
        module_id="first_steps",
        loop_count=3,
        days_per_loop=3,
        rule_y_id="fs_murder_plan",
        rule_x_ids=["fs_ripper_shadow"],
        characters=[
            CharacterDraft("male_student", "mastermind"),
            CharacterDraft("female_student", "key_person"),
            CharacterDraft("idol", "rumormonger"),
            CharacterDraft("office_worker", "killer"),
            CharacterDraft("shrine_maiden", "serial_killer"),
        ],
        incidents=[
            IncidentDraft("", day=1, perpetrator_id=""),
            IncidentDraft("", day=2, perpetrator_id=""),
            IncidentDraft("suicide", day=3, perpetrator_id="female_student"),
        ],
    )


class NewGameController:
    """UI 新游戏页的最小 adapter；只把表单草稿转为 engine 输入模型。"""

    @staticmethod
    def build_character_setups(draft: NewGameDraft) -> list[CharacterSetup]:
        return [
            CharacterSetup(
                character_id=item.character_id,
                identity_id=item.identity_id,
                initial_area=item.initial_area_id,
                territory_area=item.territory_area_id,
                entry_loop=item.entry_loop,
                entry_day=item.entry_day,
            )
            for item in draft.characters
        ]

    @staticmethod
    def build_incidents(draft: NewGameDraft) -> list[IncidentSchedule]:
        return [
            IncidentSchedule(
                item.incident_id,
                day=item.day,
                perpetrator_id=item.perpetrator_id,
            )
            for item in draft.incidents
            if item.incident_id
        ]

    @staticmethod
    def build_payload(draft: NewGameDraft) -> dict[str, object]:
        return {
            "module_id": draft.module_id,
            "loop_count": draft.loop_count,
            "days_per_loop": draft.days_per_loop,
            "rule_y_id": draft.rule_y_id,
            "rule_x_ids": list(draft.rule_x_ids),
            "character_setups": NewGameController.build_character_setups(draft),
            "incidents": NewGameController.build_incidents(draft),
        }
