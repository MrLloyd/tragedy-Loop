"""测试 IncidentHandler 的触发判定与效果执行逻辑"""

from __future__ import annotations

from engine.event_bus import EventBus, GameEventType
from engine.game_state import GameState
from engine.models.character import CharacterState
from engine.models.enums import AreaId, CharacterLifeState, EffectType, Outcome, TokenType
from engine.models.effects import Condition, Effect
from engine.models.incident import IncidentDef, IncidentSchedule
from engine.models.script import CharacterSetup
from engine.models.selectors import area_choice_selector, character_choice_selector
from engine.phases.phase_base import ForceLoopEnd, IncidentHandler, PhaseComplete, WaitForInput
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver
from engine.resolvers.incident_resolver import IncidentResolver
from engine.rules.module_loader import apply_loaded_module, load_module


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _make_handler() -> tuple[IncidentHandler, EventBus]:
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    handler = IncidentHandler(bus, resolver)
    return handler, bus


def _make_state_with_incident(
    *,
    paranoia: int = 0,
    paranoia_limit: int = 2,
    day: int = 1,
    incident_id: str = "test_incident",
    perpetrator_id: str = "perp",
    life_state: CharacterLifeState = CharacterLifeState.ALIVE,
    incident_def: IncidentDef | None = None,
) -> GameState:
    """构造一个含单条事件日程的最小游戏状态"""
    state = GameState.create_minimal_test_state(days_per_loop=3)
    state.current_day = day

    # 当事人角色
    state.characters[perpetrator_id] = CharacterState(
        character_id=perpetrator_id,
        name="当事人",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=paranoia_limit,
    )
    state.characters[perpetrator_id].life_state = life_state
    state.characters[perpetrator_id].tokens.paranoia = paranoia

    # 事件日程
    state.script.incidents = [
        IncidentSchedule(
            incident_id=incident_id,
            day=day,
            perpetrator_id=perpetrator_id,
        )
    ]

    # 注入 IncidentDef（可选）
    if incident_def is not None:
        state.incident_defs[incident_id] = incident_def

    return state


# ---------------------------------------------------------------------------
# 测试 1：不安不足，不触发
# ---------------------------------------------------------------------------

def test_incident_does_not_trigger_when_paranoia_below_limit() -> None:
    handler, bus = _make_handler()
    state = _make_state_with_incident(paranoia=1, paranoia_limit=2)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert not state.script.incidents[0].occurred
    assert state.incidents_occurred_this_loop == []


# ---------------------------------------------------------------------------
# 测试 2：当事人已死亡，不触发
# ---------------------------------------------------------------------------

def test_incident_does_not_trigger_when_perpetrator_dead() -> None:
    handler, bus = _make_handler()
    state = _make_state_with_incident(paranoia=5, paranoia_limit=2, life_state=CharacterLifeState.DEAD)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert not state.script.incidents[0].occurred


def test_suppressed_incident_is_blocked_before_forced_occurrence(monkeypatch) -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = _make_state_with_incident(paranoia=0, paranoia_limit=2)
    state.suppressed_incident_perpetrators.add("perp")
    monkeypatch.setattr(resolver, "_incident_is_forced", lambda *_args, **_kwargs: True)

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is False
    assert state.script.incidents[0].occurred is False
    assert state.incidents_occurred_this_loop == []


def test_forced_incident_can_bypass_normal_threshold(monkeypatch) -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = _make_state_with_incident(paranoia=0, paranoia_limit=2)
    monkeypatch.setattr(resolver, "_incident_is_forced", lambda *_args, **_kwargs: True)

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.script.incidents[0].occurred is True
    assert state.incidents_occurred_this_loop == ["test_incident"]


def test_forced_incident_does_not_bypass_dead_perpetrator_blocker(monkeypatch) -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = _make_state_with_incident(paranoia=0, paranoia_limit=2, life_state=CharacterLifeState.DEAD)
    monkeypatch.setattr(resolver, "_incident_is_forced", lambda *_args, **_kwargs: True)

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is False
    assert state.script.incidents[0].occurred is False


# ---------------------------------------------------------------------------
# 测试 3：满足条件，触发标记与事件发出
# ---------------------------------------------------------------------------

def test_incident_triggers_and_marks_occurred() -> None:
    handler, bus = _make_handler()

    emitted: list = []
    bus.subscribe(GameEventType.INCIDENT_OCCURRED, emitted.append)

    state = _make_state_with_incident(paranoia=2, paranoia_limit=2)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.script.incidents[0].occurred
    assert "test_incident" in state.incidents_occurred_this_loop
    assert len(emitted) == 1
    assert emitted[0].data["incident_id"] == "test_incident"
    assert emitted[0].data["perpetrator_id"] == "perp"


def test_incident_reports_no_phenomenon_when_no_effect_runs() -> None:
    handler, bus = _make_handler()
    state = _make_state_with_incident(paranoia=2, paranoia_limit=2)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    reports = [
        event
        for event in bus.log
        if event.event_type == GameEventType.INCIDENT_PHENOMENON_REPORTED
    ]
    assert len(reports) == 1
    assert reports[0].data["incident_id"] == "test_incident"
    assert reports[0].data["day"] == 1
    assert reports[0].data["has_phenomenon"] is False
    occurred_index = next(
        index
        for index, event in enumerate(bus.log)
        if event.event_type == GameEventType.INCIDENT_OCCURRED
    )
    report_index = next(
        index
        for index, event in enumerate(bus.log)
        if event.event_type == GameEventType.INCIDENT_PHENOMENON_REPORTED
    )
    assert occurred_index < report_index


def test_incident_reports_phenomenon_after_effect_resolution() -> None:
    handler, bus = _make_handler()
    incident_def = IncidentDef(
        incident_id="test_incident",
        name="测试事件",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target="school",
                token_type=TokenType.INTRIGUE,
                amount=1,
            )
        ],
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_def=incident_def,
    )

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    reports = [
        event
        for event in bus.log
        if event.event_type == GameEventType.INCIDENT_PHENOMENON_REPORTED
    ]
    assert len(reports) == 1
    assert reports[0].data["has_phenomenon"] is True
    occurred_index = next(
        index
        for index, event in enumerate(bus.log)
        if event.event_type == GameEventType.INCIDENT_OCCURRED
    )
    token_index = next(
        index
        for index, event in enumerate(bus.log)
        if event.event_type == GameEventType.TOKEN_CHANGED
    )
    report_index = next(
        index
        for index, event in enumerate(bus.log)
        if event.event_type == GameEventType.INCIDENT_PHENOMENON_REPORTED
    )
    assert occurred_index < token_index < report_index


def test_temp_worker_and_alt_trigger_same_incident_with_simultaneous_resolution() -> None:
    handler, bus = _make_handler()
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    state.characters["temp_worker"] = CharacterState(
        character_id="temp_worker",
        name="临时工",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=1,
    )
    state.characters["temp_worker_alt"] = CharacterState(
        character_id="temp_worker_alt",
        name="临时工？",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=1,
    )
    state.characters["temp_worker"].tokens.paranoia = 1
    state.characters["temp_worker_alt"].tokens.paranoia = 1
    state.script.incidents = [
        IncidentSchedule(
            incident_id="murder",
            day=1,
            perpetrator_id="temp_worker",
            target_character_ids=["temp_worker_alt", "temp_worker"],
        )
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["temp_worker"].life_state == CharacterLifeState.DEAD
    assert state.characters["temp_worker_alt"].life_state == CharacterLifeState.DEAD
    occurred_events = [event for event in bus.log if event.event_type == GameEventType.INCIDENT_OCCURRED]
    assert len(occurred_events) == 2
    assert {event.data["perpetrator_id"] for event in occurred_events} == {"temp_worker", "temp_worker_alt"}
    assert len(state.incident_results_this_loop) == 2
    assert all(item.occurred for item in state.incident_results_this_loop)


# ---------------------------------------------------------------------------
# 测试 4：无 incident_defs 时安全降级
# ---------------------------------------------------------------------------

def test_incident_triggers_without_defs_no_crash() -> None:
    """incident_defs 为空时：触发标记正常，不执行效果，不崩溃"""
    handler, bus = _make_handler()
    state = _make_state_with_incident(paranoia=3, paranoia_limit=2, incident_def=None)

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.script.incidents[0].occurred
    assert "test_incident" in state.incidents_occurred_this_loop


# ---------------------------------------------------------------------------
# 测试 5：事件效果产生主人公死亡 → ForceLoopEnd
# ---------------------------------------------------------------------------

def test_incident_protagonist_death_returns_force_loop_end() -> None:
    death_effect = Effect(effect_type=EffectType.PROTAGONIST_DEATH, value="incident")
    incident_def = IncidentDef(
        incident_id="fatal_incident",
        name="致命事件",
        module="test",
        effects=[death_effect],
        sequential=False,
        extra_condition=None,
        is_crowd_event=False,
        required_corpse_count=0,
        modifies_paranoia_limit=0,
        no_ex_gauge_increment=False,
        ex_gauge_increment=0,
        description="",
    )

    handler, bus = _make_handler()
    state = _make_state_with_incident(
        paranoia=3,
        paranoia_limit=2,
        incident_id="fatal_incident",
        incident_def=incident_def,
    )

    signal = handler.execute(state)

    assert isinstance(signal, ForceLoopEnd)
    assert signal.reason == "fatal_incident"


def test_ai_incident_check_counts_all_tokens_as_paranoia() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="spiritual_contamination",
        name="邪气污染",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target="shrine",
                token_type=TokenType.INTRIGUE,
                amount=2,
            )
        ],
    )
    state = _make_state_with_incident(
        paranoia=0,
        paranoia_limit=4,
        incident_id="spiritual_contamination",
        perpetrator_id="ai",
        incident_def=incident_def,
    )
    state.characters["ai"].tokens.intrigue = 4

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.board.areas[AreaId.SHRINE].tokens.intrigue == 2


def test_hermit_incident_threshold_uses_scripted_x_value() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="hermit_x_gate",
        name="仙人X阈值",
        module="test",
        effects=[Effect(effect_type=EffectType.NO_EFFECT)],
    )
    state = _make_state_with_incident(
        paranoia=0,
        paranoia_limit=2,
        incident_id="hermit_x_gate",
        perpetrator_id="hermit",
        incident_def=incident_def,
    )
    state.characters["hermit"].character_id = "hermit"
    state.script.private_table.characters = [
        CharacterSetup(character_id="hermit", identity_id="平民", hermit_x=0),
    ]

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.script.incidents[0].occurred is True


def test_black_cat_incident_effect_is_overridden_to_no_phenomenon() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="test_intrigue_incident",
        name="测试密谋事件",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={
                    "scope": "fixed_area",
                    "subject": "board",
                    "area": "shrine",
                },
                token_type=TokenType.INTRIGUE,
                amount=2,
            )
        ],
    )
    state = _make_state_with_incident(
        paranoia=0,
        paranoia_limit=0,
        incident_id="test_intrigue_incident",
        perpetrator_id="black_cat",
        incident_def=incident_def,
    )
    state.characters["black_cat"].character_id = "black_cat"

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert result.has_phenomenon is False
    assert result.mutations == []
    assert state.board.areas[AreaId.SHRINE].tokens.intrigue == 0


def test_hermit_disappearance_moves_self_but_resolves_same_area_effect_on_clockwise_area() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["hermit"] = CharacterState(
        character_id="hermit",
        name="仙人",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["hermit"].tokens.paranoia = 2
    state.script.private_table.characters = [
        CharacterSetup(character_id="hermit", identity_id="平民", hermit_x=2),
    ]

    disappearance = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "disappearance",
            day=1,
            perpetrator_id="hermit",
            target_selectors=[area_choice_selector("hospital")],
            target_area_ids=["hospital"],
        ),
    )

    assert disappearance.has_phenomenon is True
    assert state.characters["hermit"].area == AreaId.HOSPITAL
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 1
    assert state.board.areas[AreaId.HOSPITAL].tokens.intrigue == 0


def test_hermit_twins_incident_can_use_counterclockwise_override_area() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="hermit_twins_area",
        name="仙人双胞胎区域",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={"scope": "same_area", "subject": "board"},
                token_type=TokenType.INTRIGUE,
                amount=1,
            )
        ],
    )
    state = _make_state_with_incident(
        paranoia=1,
        paranoia_limit=1,
        incident_id="hermit_twins_area",
        perpetrator_id="hermit",
        incident_def=incident_def,
    )
    state.characters["hermit"].character_id = "hermit"
    state.characters["hermit"].area = AreaId.SHRINE
    state.characters["hermit"].initial_area = AreaId.SHRINE
    state.characters["hermit"].identity_id = "twins"
    state.characters["hermit"].original_identity_id = "twins"
    state.script.private_table.characters = [
        CharacterSetup(character_id="hermit", identity_id="twins", hermit_x=1),
    ]
    state.script.incidents[0].perpetrator_area = AreaId.HOSPITAL.value

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.board.areas[AreaId.HOSPITAL].tokens.intrigue == 1
    assert state.board.areas[AreaId.CITY].tokens.intrigue == 0


def test_cult_leader_incident_threshold_applies_modifier_twice() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="spree_like",
        name="类猎奇杀人",
        module="test",
        effects=[Effect(effect_type=EffectType.NO_EFFECT)],
        modifies_paranoia_limit=1,
    )
    state = _make_state_with_incident(
        paranoia=4,
        paranoia_limit=3,
        incident_id="spree_like",
        perpetrator_id="cult_leader",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is False
    assert state.script.incidents[0].occurred is False


def test_cult_leader_incident_resolves_effects_twice_in_order() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="double_effect",
        name="双次结算事件",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={"ref": "self"},
                token_type=TokenType.PARANOIA,
                amount=1,
            )
        ],
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_id="double_effect",
        perpetrator_id="cult_leader",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.characters["cult_leader"].tokens.paranoia == 4
    assert len(result.mutations) == 2


def test_cult_leader_incident_repeats_ex_gauge_increment_twice() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="double_ex",
        name="双次EX变化事件",
        module="test",
        effects=[Effect(effect_type=EffectType.NO_EFFECT)],
        ex_gauge_increment=1,
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_id="double_ex",
        perpetrator_id="cult_leader",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.ex_gauge == 2


def test_normal_incident_applies_ex_gauge_increment_once() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="single_ex",
        name="单次EX变化事件",
        module="test",
        effects=[Effect(effect_type=EffectType.NO_EFFECT)],
        ex_gauge_increment=1,
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_id="single_ex",
        perpetrator_id="perp",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.ex_gauge == 1


def test_cult_leader_incident_stops_second_resolution_after_protagonist_loss() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="double_but_stop",
        name="第一次终局即停止",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={"scope": "fixed_area", "subject": "board", "area": "school"},
                token_type=TokenType.INTRIGUE,
                amount=1,
            ),
            Effect(
                effect_type=EffectType.PROTAGONIST_DEATH,
                target={"ref": "self"},
                value="incident",
            ),
        ],
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_id="double_but_stop",
        perpetrator_id="cult_leader",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert result.outcome == Outcome.PROTAGONIST_DEATH
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 1


def test_cult_leader_death_in_first_resolution_does_not_block_second_resolution() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="double_even_if_dead",
        name="教主死亡后仍继续第二次",
        module="test",
        sequential=True,
        effects=[
            Effect(
                effect_type=EffectType.KILL_CHARACTER,
                target={"ref": "self"},
            ),
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target={"scope": "fixed_area", "subject": "board", "area": "city"},
                token_type=TokenType.INTRIGUE,
                amount=1,
            ),
        ],
    )
    state = _make_state_with_incident(
        paranoia=2,
        paranoia_limit=2,
        incident_id="double_even_if_dead",
        perpetrator_id="cult_leader",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred is True
    assert state.characters["cult_leader"].life_state == CharacterLifeState.DEAD
    assert state.board.areas[AreaId.CITY].tokens.intrigue == 2


def test_resolve_effect_only_executes_effect_without_marking_incident_occurred() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    incident_def = IncidentDef(
        incident_id="effect_only_incident",
        name="仅效果事件",
        module="test",
        effects=[
            Effect(
                effect_type=EffectType.PLACE_TOKEN,
                target="target",
                token_type=TokenType.INTRIGUE,
                amount=1,
            )
        ],
    )
    state = GameState.create_minimal_test_state(days_per_loop=3)
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    schedule = IncidentSchedule(
        "effect_only_incident",
        day=1,
        perpetrator_id="perp",
    )

    result = resolver.resolve_effect_only(state, schedule, incident_def)

    assert result.occurred is False
    assert schedule.occurred is False
    assert state.characters["target"].tokens.intrigue == 1
    assert state.incidents_occurred_this_loop == []
    assert state.incident_results_this_loop == []
    assert not any(event.event_type == GameEventType.INCIDENT_OCCURRED for event in bus.log)


# ---------------------------------------------------------------------------
# 测试 6：结构化同区域全体目标 — 杀死同区域全部存活角色
# ---------------------------------------------------------------------------

def test_incident_same_area_all_kills_all_in_area() -> None:
    kill_all = Effect(
        effect_type=EffectType.KILL_CHARACTER,
        target={"scope": "same_area", "subject": "character", "mode": "all"},
    )
    incident_def = IncidentDef(
        incident_id="mass_incident",
        name="群体事件",
        module="test",
        effects=[kill_all],
        sequential=False,
        extra_condition=None,
        is_crowd_event=False,
        required_corpse_count=0,
        modifies_paranoia_limit=0,
        no_ex_gauge_increment=False,
        ex_gauge_increment=0,
        description="",
    )

    handler, bus = _make_handler()
    state = _make_state_with_incident(
        paranoia=3,
        paranoia_limit=2,
        incident_id="mass_incident",
        incident_def=incident_def,
    )

    # 在当事人同区域再加一个角色
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="受害者",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )

    handler.execute(state)

    # 当事人和受害者都应死亡
    assert state.characters["perp"].life_state == CharacterLifeState.DEAD
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD


def test_incident_resolver_public_result_does_not_expose_perpetrator() -> None:
    """公开结果只描述事件和现象，不包含当事人。"""
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = _make_state_with_incident(paranoia=3, paranoia_limit=2)

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert result.occurred
    assert result.public_result is not None
    assert result.public_result.incident_id == "test_incident"
    assert result.public_result.occurred
    assert not hasattr(result.public_result, "perpetrator_id")
    assert len(state.incident_results_this_loop) == 1
    assert state.incident_results_this_loop[0] == result.public_result
    assert not hasattr(state.incident_results_this_loop[0], "perpetrator_id")


def test_incident_resolver_respects_extra_condition() -> None:
    """事件专属条件由 IncidentResolver 处理，方便后续扩展特殊机制。"""
    incident_def = IncidentDef(
        incident_id="final_day_incident",
        name="最终日事件",
        module="test",
        effects=[Effect(effect_type=EffectType.NO_EFFECT)],
        extra_condition=Condition(condition_type="is_final_day"),
    )
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = _make_state_with_incident(
        paranoia=3,
        paranoia_limit=2,
        day=1,
        incident_id="final_day_incident",
        incident_def=incident_def,
    )

    result = resolver.resolve_schedule(state, state.script.incidents[0])

    assert not result.occurred
    assert not state.script.incidents[0].occurred
    assert len(state.incident_results_this_loop) == 1
    assert state.incident_results_this_loop[0].occurred is False


def test_first_steps_and_btx_incident_pool_matches_appendix_subset() -> None:
    assert set(load_module("first_steps").incident_defs) == {
        "unease_spread",
        "murder",
        "hospital_accident",
        "suicide",
        "spread",
        "disappearance",
        "long_range_murder",
    }
    assert set(load_module("basic_tragedy_x").incident_defs) == {
        "unease_spread",
        "murder",
        "spiritual_contamination",
        "hospital_accident",
        "suicide",
        "spread",
        "butterfly_effect",
        "disappearance",
        "long_range_murder",
    }


def test_hospital_accident_uses_board_intrigue_thresholds() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["perp"].tokens.paranoia = 2
    state.characters["victim"] = CharacterState(
        character_id="victim",
        name="受害者",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )
    schedule = IncidentSchedule("hospital_accident", day=1, perpetrator_id="perp")

    result = resolver.resolve_schedule(state, schedule)
    assert result.occurred is True
    assert result.has_phenomenon is False
    assert state.characters["victim"].life_state == CharacterLifeState.ALIVE

    schedule = IncidentSchedule("hospital_accident", day=1, perpetrator_id="perp")
    state.board.areas[AreaId.HOSPITAL].tokens.intrigue = 1
    result = resolver.resolve_schedule(state, schedule)
    assert result.has_phenomenon is True
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD
    assert state.protagonist_dead is False


def test_incident_without_legal_target_still_occurs_but_has_no_phenomenon() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["perp"].tokens.paranoia = 2

    murder = resolver.resolve_schedule(state, IncidentSchedule("murder", day=1, perpetrator_id="perp"))
    remote = resolver.resolve_schedule(state, IncidentSchedule("long_range_murder", day=1, perpetrator_id="perp"))

    assert murder.occurred is True and murder.has_phenomenon is False
    assert remote.occurred is True and remote.has_phenomenon is False
    assert state.incident_results_this_loop[-2].has_phenomenon is False
    assert state.incident_results_this_loop[-1].has_phenomenon is False


def test_murder_uses_scripted_character_choice_and_excludes_perpetrator() -> None:
    handler, _ = _make_handler()
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    for cid in ("perp", "victim"):
        state.characters[cid] = CharacterState(
            character_id=cid,
            name=cid,
            area=AreaId.CITY,
            initial_area=AreaId.CITY,
            identity_id="平民",
            original_identity_id="平民",
            paranoia_limit=2,
        )
    state.characters["perp"].tokens.paranoia = 2
    state.script.incidents = [
        IncidentSchedule(
            "murder",
            day=1,
            perpetrator_id="perp",
            target_selectors=[character_choice_selector("victim")],
            target_character_ids=["victim"],
        )
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["perp"].life_state == CharacterLifeState.ALIVE
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD


def test_incident_resolver_does_not_auto_pick_character_when_choice_missing() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    for cid in ("perp", "victim"):
        state.characters[cid] = CharacterState(
            character_id=cid,
            name=cid,
            area=AreaId.CITY,
            initial_area=AreaId.CITY,
            identity_id="平民",
            original_identity_id="平民",
            paranoia_limit=2,
        )
    state.characters["perp"].tokens.paranoia = 2

    result = resolver.resolve_schedule(
        state,
        IncidentSchedule("murder", day=1, perpetrator_id="perp"),
    )

    assert result.occurred is True
    assert result.has_phenomenon is False
    assert state.characters["perp"].life_state == CharacterLifeState.ALIVE
    assert state.characters["victim"].life_state == CharacterLifeState.ALIVE


def test_long_range_murder_can_only_target_character_with_two_intrigue() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    for cid in ("perp", "safe", "victim"):
        state.characters[cid] = CharacterState(
            character_id=cid,
            name=cid,
            area=AreaId.CITY,
            initial_area=AreaId.CITY,
            identity_id="平民",
            original_identity_id="平民",
            paranoia_limit=2,
        )
    state.characters["perp"].tokens.paranoia = 2
    state.characters["safe"].tokens.intrigue = 1
    state.characters["victim"].tokens.intrigue = 2

    result = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "long_range_murder",
            day=1,
            perpetrator_id="perp",
            target_character_ids=["safe", "victim"],
        ),
    )

    assert result.occurred is True
    assert result.has_phenomenon is True
    assert state.characters["safe"].life_state == CharacterLifeState.ALIVE
    assert state.characters["victim"].life_state == CharacterLifeState.DEAD


def test_butterfly_effect_without_token_choice_occurs_but_has_no_phenomenon() -> None:
    handler, _ = _make_handler()
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    for cid in ("perp", "target"):
        state.characters[cid] = CharacterState(
            character_id=cid,
            name=cid,
            area=AreaId.CITY,
            initial_area=AreaId.CITY,
            identity_id="平民",
            original_identity_id="平民",
            paranoia_limit=2,
        )
    state.characters["perp"].tokens.paranoia = 2
    state.script.incidents = [
        IncidentSchedule(
            "butterfly_effect",
            day=1,
            perpetrator_id="perp",
            target_character_ids=["target"],
        )
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["target"].tokens.intrigue == 0
    assert state.incident_results_this_loop[-1].occurred is True
    assert state.incident_results_this_loop[-1].has_phenomenon is False


def test_unease_spread_and_spread_use_hidden_targets_in_order() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("first_steps"))
    state.current_day = 1
    for cid in ("perp", "a", "b"):
        state.characters[cid] = CharacterState(
            character_id=cid,
            name=cid,
            area=AreaId.SCHOOL,
            initial_area=AreaId.SCHOOL,
            identity_id="平民",
            original_identity_id="平民",
            paranoia_limit=2,
        )
    state.characters["perp"].tokens.paranoia = 2
    state.characters["a"].tokens.goodwill = 2

    unease = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "unease_spread",
            day=1,
            perpetrator_id="perp",
            target_character_ids=["a", "b"],
        ),
    )
    assert unease.has_phenomenon is True
    assert state.characters["a"].tokens.paranoia == 2
    assert state.characters["b"].tokens.intrigue == 1

    spread = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "spread",
            day=1,
            perpetrator_id="perp",
            target_character_ids=["a", "b"],
        ),
    )
    assert spread.has_phenomenon is True
    assert state.characters["a"].tokens.goodwill == 0
    assert state.characters["b"].tokens.goodwill == 2


def test_incident_resolver_can_use_supplied_area_and_token_choices() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["target"] = CharacterState(
        character_id="target",
        name="目标",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["perp"].tokens.paranoia = 2

    disappearance = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "disappearance",
            day=1,
            perpetrator_id="perp",
            target_selectors=[area_choice_selector("school")],
            target_area_ids=["school"],
        ),
    )
    assert disappearance.has_phenomenon is True
    assert state.characters["perp"].area == AreaId.SCHOOL
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 1

    state.characters["perp"].area = AreaId.CITY
    state.characters["target"].area = AreaId.CITY
    butterfly = resolver.resolve_schedule(
        state,
        IncidentSchedule(
            "butterfly_effect",
            day=1,
            perpetrator_id="perp",
            target_character_ids=["target"],
            chosen_token_types=["intrigue"],
        ),
    )
    assert butterfly.has_phenomenon is True
    assert state.characters["target"].tokens.intrigue == 1


def test_disappearance_runtime_choice_excludes_forbidden_areas() -> None:
    bus = EventBus()
    resolver = IncidentResolver(bus, AtomicResolver(bus, DeathResolver()))
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
        base_forbidden_areas=[AreaId.HOSPITAL, AreaId.CITY],
        forbidden_areas=[AreaId.HOSPITAL, AreaId.CITY],
    )
    state.characters["perp"].tokens.paranoia = 2

    schedule = IncidentSchedule(
        "disappearance",
        day=1,
        perpetrator_id="perp",
        target_selectors=[area_choice_selector(AreaId.HOSPITAL.value)],
        target_area_ids=[AreaId.HOSPITAL.value],
    )
    incident_def = state.incident_defs["disappearance"]

    assert resolver.next_runtime_choice(state, schedule, incident_def) == (
        "area",
        [AreaId.SCHOOL.value, AreaId.SHRINE.value],
    )

    disappearance = resolver.resolve_schedule(state, schedule)

    assert disappearance.has_phenomenon is False
    assert state.characters["perp"].area == AreaId.SHRINE
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 0
    assert state.board.areas[AreaId.HOSPITAL].tokens.intrigue == 0


def test_disappearance_without_area_choice_occurs_but_has_no_phenomenon() -> None:
    handler, _ = _make_handler()
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["perp"] = CharacterState(
        character_id="perp",
        name="当事人",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["perp"].tokens.paranoia = 2
    state.script.incidents = [
        IncidentSchedule("disappearance", day=1, perpetrator_id="perp")
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["perp"].area == AreaId.CITY
    assert state.incident_results_this_loop[-1].occurred is True
    assert state.incident_results_this_loop[-1].has_phenomenon is False


def test_disappearance_moves_servant_with_perpetrator_before_following_effects() -> None:
    handler, _ = _make_handler()
    state = GameState.create_minimal_test_state(days_per_loop=3)
    apply_loaded_module(state, load_module("basic_tragedy_x"))
    state.current_day = 1
    state.characters["ojousama"] = CharacterState(
        character_id="ojousama",
        name="大小姐",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
        paranoia_limit=2,
    )
    state.characters["servant"] = CharacterState(
        character_id="servant",
        name="从者",
        area=AreaId.CITY,
        initial_area=AreaId.CITY,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["ojousama"].tokens.paranoia = 2
    state.script.incidents = [
        IncidentSchedule(
            "disappearance",
            day=1,
            perpetrator_id="ojousama",
            target_selectors=[area_choice_selector("school")],
            target_area_ids=["school"],
        )
    ]

    signal = handler.execute(state)

    assert isinstance(signal, PhaseComplete)
    assert state.characters["ojousama"].area == AreaId.SCHOOL
    assert state.characters["servant"].area == AreaId.SCHOOL
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 1
