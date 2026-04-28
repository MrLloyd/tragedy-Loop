"""Phase 3: 行动牌系统完整测试"""

from __future__ import annotations

from engine.event_bus import EventBus
from engine.game_state import GameState
from engine.models.cards import ActionCard, CardPlacement, PlacementIntent, create_mastermind_hand, create_protagonist_hand
from engine.models.character import CharacterState
from engine.models.enums import AreaId, CardType, CharacterLifeState, EffectType, PlayerRole, TokenType, Trait
from engine.phases.phase_base import ActionResolveHandler, MastermindActionHandler, ProtagonistActionHandler, PhaseComplete, WaitForInput
from engine.resolvers.atomic_resolver import AtomicResolver
from engine.resolvers.death_resolver import DeathResolver


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _make_action_handlers() -> tuple[MastermindActionHandler, ProtagonistActionHandler, ActionResolveHandler, EventBus]:
    """创建行动牌处理器"""
    bus = EventBus()
    resolver = AtomicResolver(bus, DeathResolver())
    mm_handler = MastermindActionHandler(bus, resolver)
    pp_handler = ProtagonistActionHandler(bus, resolver)
    act_handler = ActionResolveHandler(bus, resolver)
    return mm_handler, pp_handler, act_handler, bus


class SpyAtomicResolver(AtomicResolver):
    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, DeathResolver())
        self.calls: list[dict[str, object]] = []

    def resolve(self, state: GameState, effects: list, sequential: bool = False, perpetrator_id: str = ""):
        self.calls.append(
            {
                "effects": list(effects),
                "sequential": sequential,
                "perpetrator_id": perpetrator_id,
            }
        )
        return super().resolve(
            state,
            effects,
            sequential=sequential,
            perpetrator_id=perpetrator_id,
        )


def _make_state_for_placement() -> GameState:
    """构造用于放牌的最小游戏状态"""
    state = GameState.create_minimal_test_state(days_per_loop=5)
    state.current_day = 1
    state.current_loop = 1
    state.leader_index = 0

    # 初始化 3 名主人公手牌
    state.protagonist_hands = [
        create_protagonist_hand(PlayerRole.PROTAGONIST_0),
        create_protagonist_hand(PlayerRole.PROTAGONIST_1),
        create_protagonist_hand(PlayerRole.PROTAGONIST_2),
    ]

    # 剧作家手牌
    state.mastermind_hand = create_mastermind_hand()

    # 添加测试角色
    state.characters["char_1"] = CharacterState(
        character_id="char_1",
        name="角色1",
        area=AreaId.HOSPITAL,
        initial_area=AreaId.HOSPITAL,
        identity_id="平民",
        original_identity_id="平民",
    )
    state.characters["char_2"] = CharacterState(
        character_id="char_2",
        name="角色2",
        area=AreaId.SCHOOL,
        initial_area=AreaId.SCHOOL,
        identity_id="平民",
        original_identity_id="平民",
        base_traits={Trait.NO_ACTION_CARDS},  # 不可放置行动牌
    )
    state.characters["char_3"] = CharacterState(
        character_id="char_3",
        name="角色3（已死亡）",
        area=AreaId.SHRINE,
        initial_area=AreaId.SHRINE,
        identity_id="平民",
        original_identity_id="平民",
        life_state=CharacterLifeState.DEAD,
    )

    return state


# ---------------------------------------------------------------------------
# T1: 剧作家提交3张合法牌（2角色目标+1版图目标）
# ---------------------------------------------------------------------------

def test_mastermind_place_3_cards():
    """剧作家逐次放置3张牌，目标混合角色和版图"""
    mm_handler, _, _, _ = _make_action_handlers()
    state = _make_state_for_placement()

    intents = [
        PlacementIntent(
            card=state.mastermind_hand.cards[0],  # INTRIGUE_PLUS_2
            target_type="character",
            target_id="char_1",
        ),
        PlacementIntent(
            card=state.mastermind_hand.cards[1],  # INTRIGUE_PLUS_1
            target_type="board",
            target_id=AreaId.SCHOOL.value,
        ),
        PlacementIntent(
            card=state.mastermind_hand.cards[2],  # PARANOIA_PLUS_1
            target_type="board",
            target_id=AreaId.HOSPITAL.value,
        ),
    ]

    signal = mm_handler.execute(state)
    assert isinstance(signal, WaitForInput)
    assert signal.input_type == "place_action_card"
    assert signal.player == "mastermind"

    signal = signal.callback(intents[0])
    assert isinstance(signal, WaitForInput)
    signal = signal.callback(intents[1])
    assert isinstance(signal, WaitForInput)
    result = signal.callback(intents[2])
    assert isinstance(result, PhaseComplete)

    # 验证放置记录
    assert len(state.placed_cards) == 3
    assert state.placed_cards[0].target_type == "character"
    assert state.placed_cards[0].target_id == "char_1"
    assert state.placed_cards[1].target_type == "board"
    assert state.placed_cards[1].target_id == AreaId.SCHOOL.value
    assert state.placed_cards[2].target_type == "board"
    assert state.placed_cards[2].target_id == AreaId.HOSPITAL.value


# ---------------------------------------------------------------------------
# T2: 剧作家不能在同一位置叠放自身行动牌
# ---------------------------------------------------------------------------

def test_mastermind_rejects_duplicate_slot():
    """同一剧作家的 3 张行动牌不能放到同一目标"""
    mm_handler, _, _, _ = _make_action_handlers()
    state = _make_state_for_placement()

    signal = mm_handler.execute(state)
    assert isinstance(signal, WaitForInput)

    next_signal = signal.callback(
        PlacementIntent(state.mastermind_hand.cards[0], "board", AreaId.SCHOOL.value)
    )
    assert isinstance(next_signal, WaitForInput)

    try:
        next_signal.callback(
            PlacementIntent(state.mastermind_hand.cards[1], "board", AreaId.SCHOOL.value)
        )
        assert False, "should raise ValueError for duplicate slot"
    except ValueError as e:
        assert "same target" in str(e)


# ---------------------------------------------------------------------------
# T3: 提交含 NO_ACTION_CARDS 角色为目标 → ValueError
# ---------------------------------------------------------------------------

def test_mastermind_no_action_cards_trait():
    """目标角色有 NO_ACTION_CARDS 特性应该拒绝"""
    mm_handler, _, _, _ = _make_action_handlers()
    state = _make_state_for_placement()

    signal = mm_handler.execute(state)
    assert isinstance(signal, WaitForInput)

    try:
        signal.callback(
            PlacementIntent(state.mastermind_hand.cards[0], "character", "char_2")
        )
        assert False, "should raise ValueError for NO_ACTION_CARDS"
    except ValueError as e:
        assert "NO_ACTION_CARDS" in str(e) or "cannot receive" in str(e)


def test_mastermind_no_action_cards_runtime_trait_layer():
    """运行时派生 trait 也应该阻止行动牌放置"""
    mm_handler, _, _, _ = _make_action_handlers()
    state = _make_state_for_placement()
    state.characters["char_1"].derived_traits.add(Trait.NO_ACTION_CARDS)

    signal = mm_handler.execute(state)
    assert isinstance(signal, WaitForInput)

    try:
        signal.callback(
            PlacementIntent(state.mastermind_hand.cards[0], "character", "char_1")
        )
        assert False, "should raise ValueError for runtime NO_ACTION_CARDS"
    except ValueError as e:
        assert "NO_ACTION_CARDS" in str(e) or "cannot receive" in str(e)


# ---------------------------------------------------------------------------
# T4: 3名主人公依次放牌（从 leader_index 起）
# ---------------------------------------------------------------------------

def test_protagonist_all_three_place_cards():
    """3名主人公各放1张牌"""
    _, pp_handler, _, _ = _make_action_handlers()
    state = _make_state_for_placement()
    state.leader_index = 0

    # 第 1 个主人公（队长，索引0）
    signal1 = pp_handler.execute(state)
    assert isinstance(signal1, WaitForInput)
    assert signal1.player == "protagonist_0"

    intent1 = PlacementIntent(
        card=state.protagonist_hands[0].cards[0],
        target_type="board",
        target_id=AreaId.SCHOOL.value,
    )
    signal2 = signal1.callback(intent1)
    assert isinstance(signal2, WaitForInput)
    assert signal2.player == "protagonist_1"
    assert len(state.placed_cards) == 1

    # 第 2 个主人公（索引1）
    intent2 = PlacementIntent(
        card=state.protagonist_hands[1].cards[1],
        target_type="board",
        target_id=AreaId.HOSPITAL.value,
    )
    signal3 = signal2.callback(intent2)
    assert isinstance(signal3, WaitForInput)
    assert signal3.player == "protagonist_2"
    assert len(state.placed_cards) == 2

    # 第 3 个主人公（索引2）
    intent3 = PlacementIntent(
        card=state.protagonist_hands[2].cards[2],
        target_type="board",
        target_id=AreaId.SHRINE.value,
    )
    result = signal3.callback(intent3)
    assert isinstance(result, PhaseComplete)
    assert len(state.placed_cards) == 3

    # 验证所有 owner
    assert state.placed_cards[0].owner == PlayerRole.PROTAGONIST_0
    assert state.placed_cards[1].owner == PlayerRole.PROTAGONIST_1
    assert state.placed_cards[2].owner == PlayerRole.PROTAGONIST_2


def test_protagonists_reject_duplicate_slot_but_allow_mastermind_slot_overlap():
    """主人公之间不能同位叠放，但可以放到剧作家的卡位。"""
    _, pp_handler, _, _ = _make_action_handlers()
    state = _make_state_for_placement()
    state.placed_cards.append(
        CardPlacement(
            state.mastermind_hand.cards[0],
            PlayerRole.MASTERMIND,
            "board",
            AreaId.SCHOOL.value,
        )
    )

    signal1 = pp_handler.execute(state)
    assert isinstance(signal1, WaitForInput)
    signal2 = signal1.callback(
        PlacementIntent(
            state.protagonist_hands[0].cards[0],
            "board",
            AreaId.SCHOOL.value,
        )
    )
    assert isinstance(signal2, WaitForInput)

    try:
        signal2.callback(
            PlacementIntent(
                state.protagonist_hands[1].cards[0],
                "board",
                AreaId.SCHOOL.value,
            )
        )
        assert False, "should reject duplicate protagonist slot"
    except ValueError as e:
        assert "same target" in str(e)


# ---------------------------------------------------------------------------
# T5: 禁止密谋特殊结算（全场 2 张及以上同时失效）
# ---------------------------------------------------------------------------

def test_action_resolve_forbid_intrigue_global_mutual_cancel():
    """两张禁止密谋分散在不同位置时也应同时失效"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    forbid1 = ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0)
    forbid2 = ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_1)
    intrigue1 = ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND)
    intrigue2 = ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND)

    state.placed_cards = [
        CardPlacement(forbid1, PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
        CardPlacement(forbid2, PlayerRole.PROTAGONIST_1, "character", "char_2", face_down=True),
        CardPlacement(intrigue1, PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
        CardPlacement(intrigue2, PlayerRole.MASTERMIND, "character", "char_2", face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    assert state.placed_cards[0].nullified is True
    assert state.placed_cards[1].nullified is True
    assert state.placed_cards[2].nullified is False
    assert state.placed_cards[3].nullified is False
    assert state.characters["char_1"].tokens.intrigue == 1
    assert state.characters["char_2"].tokens.intrigue == 1


# ---------------------------------------------------------------------------
# T6: 单张禁止密谋正常生效
# ---------------------------------------------------------------------------

def test_action_resolve_single_forbid_intrigue_blocks_same_target_intrigue():
    """仅有一张禁止密谋时，应正常禁止同位置密谋牌"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    char_id = "char_1"

    forbid = ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0)
    intrigue = ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND)

    state.placed_cards = [
        CardPlacement(forbid, PlayerRole.PROTAGONIST_0, "character", char_id, face_down=True),
        CardPlacement(intrigue, PlayerRole.MASTERMIND, "character", char_id, face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    assert state.placed_cards[0].nullified is False
    assert state.placed_cards[1].nullified is True
    assert state.characters[char_id].tokens.intrigue == 0


def test_action_resolve_forbid_movement_still_blocks_same_target_movement():
    """其他禁止牌仍按同位置规则正常生效"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.FORBID_MOVEMENT, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.placed_cards[0].nullified is False
    assert state.placed_cards[1].nullified is True
    assert state.characters["char_1"].area == AreaId.HOSPITAL


# ---------------------------------------------------------------------------
# T7: once_per_loop 牌结算后不再 get_available()
# ---------------------------------------------------------------------------

def test_once_per_loop_marking():
    """once_per_loop 牌结算后被标记，不再出现在可用牌中"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    # 剧作家的 INTRIGUE_PLUS_2 是 once_per_loop
    once_loop_card = state.mastermind_hand.cards[0]
    assert once_loop_card.once_per_loop is True
    assert once_loop_card.is_used_this_loop is False

    available_before = state.mastermind_hand.get_available()
    assert once_loop_card in available_before

    # 放置该牌
    state.placed_cards = [
        CardPlacement(once_loop_card, PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
    ]

    # 结算（执行 ActionResolveHandler）
    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    # 验证标记
    assert once_loop_card.is_used_this_loop is True

    # 再次调用 get_available()，不应包含该牌
    available_after = state.mastermind_hand.get_available()
    assert once_loop_card not in available_after


# ---------------------------------------------------------------------------
# T8: once_per_loop 牌 nullified 后仍标记为已用
# ---------------------------------------------------------------------------

def test_once_per_loop_marked_even_when_nullified():
    """被禁止（nullified）的 once_per_loop 牌仍应标记为已用"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    char_id = "char_1"
    once_loop_card = state.mastermind_hand.cards[0]  # INTRIGUE_PLUS_2，once_per_loop
    forbid = ActionCard(CardType.FORBID_INTRIGUE, PlayerRole.PROTAGONIST_0)

    state.placed_cards = [
        CardPlacement(forbid, PlayerRole.PROTAGONIST_0, "character", char_id, face_down=True),
        CardPlacement(once_loop_card, PlayerRole.MASTERMIND, "character", char_id, face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    # 验证禁止和标记
    assert once_loop_card.is_used_this_loop is True
    assert state.placed_cards[1].nullified is True
    # 角色密谋保持 0（被禁止）
    assert state.characters[char_id].tokens.intrigue == 0


# ---------------------------------------------------------------------------
# T9: 密谋+1 放到角色 → 角色 intrigue+1
# ---------------------------------------------------------------------------

def test_token_effect_on_character():
    """指示物牌放到角色，角色指示物应增加"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    char_id = "char_1"
    assert state.characters[char_id].tokens.intrigue == 0

    card = ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND)
    state.placed_cards = [
        CardPlacement(card, PlayerRole.MASTERMIND, "character", char_id, face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    # 验证角色密谋+1
    assert state.characters[char_id].tokens.intrigue == 1


# ---------------------------------------------------------------------------
# T10: 密谋+1 放到版图区域 → 区域 intrigue+1
# ---------------------------------------------------------------------------

def test_token_effect_on_board():
    """指示物牌放到版图，版图指示物应增加"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    area_id = AreaId.SCHOOL
    assert state.board.areas[area_id].tokens.intrigue == 0

    card = ActionCard(CardType.INTRIGUE_PLUS_2, PlayerRole.MASTERMIND)
    state.placed_cards = [
        CardPlacement(card, PlayerRole.MASTERMIND, "board", area_id.value, face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    # 验证版图密谋+2
    assert state.board.areas[area_id].tokens.intrigue == 2


def test_board_intrigue_is_capped_at_three() -> None:
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    area_id = AreaId.SCHOOL
    state.board.areas[area_id].tokens.intrigue = 2
    card = ActionCard(CardType.INTRIGUE_PLUS_2, PlayerRole.MASTERMIND)
    state.placed_cards = [
        CardPlacement(card, PlayerRole.MASTERMIND, "board", area_id.value, face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.board.areas[area_id].tokens.intrigue == 3


# ---------------------------------------------------------------------------
# T11: 移动牌（横移）放到角色 → 角色移动到相邻区域
# ---------------------------------------------------------------------------

def test_movement_card_horizontal():
    """横移牌应将角色移动到相邻区域"""
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    char_id = "char_1"
    initial_area = state.characters[char_id].area
    assert initial_area == AreaId.HOSPITAL

    # 医院的横相邻是神社
    expected_dest = AreaId.SHRINE

    card = ActionCard(CardType.MOVE_HORIZONTAL, PlayerRole.MASTERMIND)
    state.placed_cards = [
        CardPlacement(card, PlayerRole.MASTERMIND, "character", char_id, face_down=True),
    ]

    result = act_handler.execute(state)
    assert isinstance(result, PhaseComplete)

    # 验证角色移动到正确区域
    assert state.characters[char_id].area == expected_dest


def test_action_resolve_batches_composed_movement_then_other_cards():
    bus = EventBus()
    resolver = SpyAtomicResolver(bus)
    handler = ActionResolveHandler(bus, resolver)
    state = _make_state_for_placement()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.MOVE_VERTICAL_P, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.INTRIGUE_PLUS_1, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "board", AreaId.SCHOOL.value, face_down=True),
        CardPlacement(ActionCard(CardType.GOODWILL_PLUS_1, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
    ]

    result = handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert len(resolver.calls) == 2

    movement_call, other_call = resolver.calls
    movement_effects = movement_call["effects"]
    other_effects = other_call["effects"]

    assert movement_call["sequential"] is False
    assert len(movement_effects) == 1
    assert movement_effects[0].effect_type == EffectType.MOVE_CHARACTER
    assert movement_effects[0].target == "char_1"
    assert movement_effects[0].value == AreaId.SCHOOL.value

    assert other_call["sequential"] is False
    assert len(other_effects) == 2
    assert all(effect.effect_type == EffectType.PLACE_TOKEN for effect in other_effects)

    assert state.characters["char_1"].area == AreaId.SCHOOL
    assert state.characters["char_1"].tokens.goodwill == 1
    assert state.board.areas[AreaId.SCHOOL].tokens.intrigue == 1


def test_movement_cards_same_target_same_direction_stays_horizontal():
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL_P, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.SHRINE


def test_movement_cards_same_target_horizontal_and_diagonal_compose_to_vertical():
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_DIAGONAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL_P, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.CITY


def test_movement_cards_same_target_vertical_and_diagonal_compose_to_horizontal():
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_DIAGONAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
        CardPlacement(ActionCard(CardType.MOVE_VERTICAL_P, PlayerRole.PROTAGONIST_0), PlayerRole.PROTAGONIST_0, "character", "char_1", face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.SHRINE


def test_movement_card_into_forbidden_area_stays_in_place():
    _, _, act_handler, _ = _make_action_handlers()
    state = _make_state_for_placement()
    state.characters["char_1"].forbidden_areas = [AreaId.SCHOOL]
    state.characters["char_1"].base_forbidden_areas = [AreaId.SCHOOL]

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_DIAGONAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
    ]

    result = act_handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.HOSPITAL


def test_movement_card_on_faraway_character_stays_in_place():
    bus = EventBus()
    resolver = SpyAtomicResolver(bus)
    handler = ActionResolveHandler(bus, resolver)
    state = _make_state_for_placement()
    state.characters["char_1"].area = AreaId.FARAWAY
    state.characters["char_1"].initial_area = AreaId.FARAWAY

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_HORIZONTAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
    ]

    result = handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.FARAWAY
    assert resolver.calls == []


def test_movement_card_on_dead_character_stays_in_place():
    bus = EventBus()
    resolver = SpyAtomicResolver(bus)
    handler = ActionResolveHandler(bus, resolver)
    state = _make_state_for_placement()
    state.characters["char_1"].mark_dead()

    state.placed_cards = [
        CardPlacement(ActionCard(CardType.MOVE_VERTICAL, PlayerRole.MASTERMIND), PlayerRole.MASTERMIND, "character", "char_1", face_down=True),
    ]

    result = handler.execute(state)

    assert isinstance(result, PhaseComplete)
    assert state.characters["char_1"].area == AreaId.HOSPITAL
    assert resolver.calls == []
