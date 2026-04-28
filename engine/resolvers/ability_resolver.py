"""惨剧轮回 — 能力收集与条件求值框架

本模块负责：
- 按时机收集角色/规则能力
- 计算角色当前生效特性
- 对声明式 Condition 做基础求值
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Optional

from engine.game_state import GameState
from engine.models.ability import Ability, AbilityLocationContext
from engine.models.effects import Condition, Effect
from engine.models.enums import AbilityTiming, AbilityType, AreaId, Attribute, EffectType, TokenType, Trait
from engine.models.selectors import TargetSelector, parse_target_selector
from engine.rules.persistent_effects import settle_persistent_effects
from engine.rules.runtime_traits import active_traits as resolve_active_traits


@dataclass(frozen=True)
class AbilityCandidate:
    """一次可结算能力的候选项。"""

    source_kind: str  # "goodwill" | "identity" | "rule" | "derived"
    source_id: str
    ability: Ability
    identity_id: Optional[str] = None


_PLAYWRIGHT_GOODWILL_ABILITY_IDS = frozenset(
    {
        "goodwill:higher_being:1",
        "goodwill:doctor:1",
    }
)
_PLAYWRIGHT_GOODWILL_TRAITS = frozenset(
    {
        Trait.IGNORE_GOODWILL,
        Trait.MUST_IGNORE_GOODWILL,
    }
)


class AbilityResolver:
    """
    能力层基础框架。

    说明：
    - 本类不直接执行 Effect，仅提供候选能力与条件判断。
    - 具体声明顺序、WaitForInput、拒绝公告由 PhaseHandler 层控制。
    """

    def collect_goodwill_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming = AbilityTiming.PROTAGONIST_ABILITY,
        ability_type: AbilityType | None = None,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        if timing != AbilityTiming.PROTAGONIST_ABILITY:
            return []
        if ability_type is not None and ability_type != AbilityType.OPTIONAL:
            return []

        result: list[AbilityCandidate] = []
        for ch in state.characters.values():
            if alive_only and not ch.is_active():
                continue

            if ch.goodwill_abilities:
                for ability in ch.goodwill_abilities:
                    if ability.timing != timing:
                        continue
                    if ability_type is not None and ability.ability_type != ability_type:
                        continue
                    if ch.tokens.goodwill < ability.goodwill_requirement:
                        continue
                    candidate = AbilityCandidate(
                        source_kind="goodwill",
                        source_id=ch.character_id,
                        ability=ability,
                    )
                    if not self.evaluate_condition(state, candidate.ability.condition, owner_id=ch.character_id):
                        continue
                    if not self.is_ability_available(state, candidate):
                        continue
                    result.append(candidate)
                continue

            texts = ch.goodwill_ability_texts
            requirements = ch.goodwill_ability_goodwill_requirements
            once_limits = ch.goodwill_ability_once_per_loop

            for slot in range(min(len(texts), len(requirements))):
                text = texts[slot].strip()
                if not text:
                    continue

                requirement = requirements[slot]
                if ch.tokens.goodwill < requirement:
                    continue

                once_per_loop = once_limits[slot] if slot < len(once_limits) else False
                ability_id = f"goodwill:{ch.character_id}:{slot + 1}"
                candidate = AbilityCandidate(
                    source_kind="goodwill",
                    source_id=ch.character_id,
                    ability=Ability(
                        ability_id=ability_id,
                        name=f"{ch.name} 友好能力{slot + 1}",
                        ability_type=AbilityType.OPTIONAL,
                        timing=AbilityTiming.PROTAGONIST_ABILITY,
                        description=text,
                        condition=self._goodwill_condition_for(ch.character_id, slot),
                        effects=self._goodwill_effects_for(ch.character_id, slot),
                        goodwill_requirement=requirement,
                        once_per_loop=once_per_loop,
                        can_be_refused=True,
                    ),
                )
                if not self.evaluate_condition(state, candidate.ability.condition, owner_id=ch.character_id):
                    continue
                if not self.is_ability_available(state, candidate):
                    continue
                result.append(candidate)
        return result

    def collect_playwright_goodwill_abilities(
        self,
        state: GameState,
        *,
        ability_type: AbilityType | None = AbilityType.OPTIONAL,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        """剧作家阶段可额外声明的友好能力入口。"""
        if ability_type is not None and ability_type != AbilityType.OPTIONAL:
            return []

        result: list[AbilityCandidate] = []
        for candidate in self.collect_goodwill_abilities(
            state,
            ability_type=AbilityType.OPTIONAL,
            alive_only=alive_only,
        ):
            if candidate.ability.ability_id not in _PLAYWRIGHT_GOODWILL_ABILITY_IDS:
                continue
            if not self._has_playwright_goodwill_trait(state, candidate.source_id):
                continue
            result.append(candidate)
        return result

    def _collect_identity_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None = None,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        settle_persistent_effects(state)
        result: list[AbilityCandidate] = []
        for ch in state.characters.values():
            if alive_only and not ch.is_active():
                continue

            identity_def = state.identity_defs.get(ch.identity_id)
            if identity_def is None:
                continue

            for ability in identity_def.abilities:
                if ability.timing != timing:
                    continue
                if ability_type is not None and ability.ability_type != ability_type:
                    continue
                if not self._evaluate_condition_for_owner_contexts(
                    state,
                    ability.condition,
                    owner_id=ch.character_id,
                ):
                    continue
                candidate = AbilityCandidate(
                    source_kind="identity",
                    source_id=ch.character_id,
                    ability=ability,
                    identity_id=identity_def.identity_id,
                )
                if not self.is_ability_available(state, candidate):
                    continue
                result.append(candidate)
        return result

    def collect_character_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None = None,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        """兼容旧接口；新代码应优先使用 `collect_abilities()`。"""
        return self._collect_identity_abilities(
            state,
            timing=timing,
            ability_type=ability_type,
            alive_only=alive_only,
        )

    def collect_rule_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None = None,
    ) -> list[AbilityCandidate]:
        result: list[AbilityCandidate] = []

        if state.script.rule_y is not None:
            result.extend(
                self._collect_from_rule(
                    state,
                    timing=timing,
                    ability_type=ability_type,
                    rule_id=state.script.rule_y.rule_id,
                    abilities=state.script.rule_y.abilities,
                )
            )

        for rule in state.script.rules_x:
            result.extend(
                self._collect_from_rule(
                    state,
                    timing=timing,
                    ability_type=ability_type,
                    rule_id=rule.rule_id,
                    abilities=rule.abilities,
                )
            )

        return result

    def collect_derived_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None = None,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        """常驻派生能力入口（P4-3）。"""
        settle_persistent_effects(state)
        result: list[AbilityCandidate] = []
        for ch in state.characters.values():
            if alive_only and not ch.is_active():
                continue

            identity_def = state.identity_defs.get(ch.identity_id)
            if identity_def is None:
                continue

            for derived_rule in identity_def.derived_identities:
                if not self.evaluate_condition(
                    state,
                    derived_rule.condition,
                    owner_id=ch.character_id,
                ):
                    continue
                result.extend(
                    self._collect_identity_as_derived(
                        state,
                        owner_id=ch.character_id,
                        derived_identity_id=derived_rule.derived_identity_id,
                        timing=timing,
                        ability_type=ability_type,
                    )
                )

        return result

    def collect_abilities(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None = None,
        alive_only: bool = True,
    ) -> list[AbilityCandidate]:
        """统一入口：角色友好 / 身份 / 规则 / 常驻派生。"""
        goodwill_candidates = self.collect_goodwill_abilities(
            state,
            timing=timing,
            ability_type=ability_type,
            alive_only=alive_only,
        )
        identity_candidates = self._collect_identity_abilities(
            state,
            timing=timing,
            ability_type=ability_type,
            alive_only=alive_only,
        )
        rule_candidates = self.collect_rule_abilities(
            state,
            timing=timing,
            ability_type=ability_type,
        )
        derived_candidates = self.collect_derived_abilities(
            state,
            timing=timing,
            ability_type=ability_type,
            alive_only=alive_only,
        )
        return [*goodwill_candidates, *identity_candidates, *rule_candidates, *derived_candidates]

    def ability_usage_key(self, candidate: AbilityCandidate) -> str:
        return f"{candidate.source_kind}:{candidate.source_id}:{candidate.ability.ability_id}"

    def is_ability_available(self, state: GameState, candidate: AbilityCandidate) -> bool:
        key = self.ability_usage_key(candidate)
        if candidate.ability.once_per_loop:
            if state.ability_runtime.usages_this_loop.get(key, 0) > 0:
                return False
        if candidate.ability.once_per_day:
            if state.ability_runtime.usages_this_day.get(key, 0) > 0:
                return False
        return True

    def mark_ability_used(self, state: GameState, candidate: AbilityCandidate) -> None:
        """能力结算成功后调用，统一记录 once-per-loop/day 次数。"""
        key = self.ability_usage_key(candidate)
        state.ability_runtime.usages_this_loop[key] = state.ability_runtime.usages_this_loop.get(key, 0) + 1
        state.ability_runtime.usages_this_day[key] = state.ability_runtime.usages_this_day.get(key, 0) + 1

    def resolve_targets(
        self,
        state: GameState,
        *,
        owner_id: str,
        selector: Any,
        condition_target: str | None = None,
        other_id: str | None = None,
        alive_only: bool = True,
        location_context: AbilityLocationContext | None = None,
    ) -> list[str]:
        """目标解析统一入口。"""
        spec = parse_target_selector(selector)
        owner = state.characters.get(owner_id)
        if spec.ref == "self":
            if owner is None or owner.is_removed():
                return []
            return [owner_id]
        if spec.ref == "none":
            return []
        if spec.ref == "condition_target":
            return self._resolve_ref_target(state, condition_target)
        if spec.ref == "literal":
            return self._resolve_ref_target(state, spec.value)
        if spec.ref == "other":
            return self._resolve_ref_target(state, other_id)
        if spec.ref == "last_loop_goodwill_characters":
            last_snapshot = state.get_last_loop_snapshot()
            if last_snapshot is None:
                return []
            return [
                character_id
                for character_id, snapshot in last_snapshot.character_snapshots.items()
                if snapshot.tokens.goodwill > 0 and character_id in state.characters
            ]
        if spec.ref == "another_character":
            return []
        if spec.subject in {"character", "other_character", "dead_character"}:
            return self._resolve_character_targets(
                state,
                owner_id=owner_id,
                owner=owner,
                spec=spec,
                alive_only=alive_only,
                location_context=location_context,
            )
        if spec.subject == "board":
            return self._resolve_board_targets(
                state=state,
                owner=owner,
                spec=spec,
                location_context=location_context,
            )
        if spec.subject == "character_or_board":
            if owner is None and spec.scope != "any_area":
                return []
            return [
                *self._resolve_character_targets(
                    state,
                    owner_id=owner_id,
                    owner=owner,
                    spec=TargetSelector(
                        scope=spec.scope,
                        subject="character",
                        mode=spec.mode,
                        filters=spec.filters,
                        area=spec.area,
                    ),
                    alive_only=alive_only,
                    location_context=location_context,
                ),
                *self._resolve_board_targets(
                    state=state,
                    owner=owner,
                    spec=TargetSelector(
                        scope=spec.scope,
                        subject="board",
                        mode=spec.mode,
                        filters=spec.filters,
                        area=spec.area,
                    ),
                    location_context=location_context,
                ),
            ]
        return []

    @staticmethod
    def _resolve_ref_target(state: GameState, target_id: str | None) -> list[str]:
        if not target_id:
            return []
        character = state.characters.get(target_id)
        if character is not None and character.is_removed():
            return []
        return [target_id]

    def _resolve_character_targets(
        self,
        state: GameState,
        *,
        owner_id: str,
        owner: Any,
        spec: TargetSelector,
        alive_only: bool,
        location_context: AbilityLocationContext | None,
    ) -> list[str]:
        if spec.scope != "any_area" and owner is None:
            return []
        area_ids = self._resolve_scope_area_ids(
            state=state,
            owner=owner,
            spec=spec,
            location_context=location_context,
        )
        targets: list[str] = []
        for ch in state.characters.values():
            if area_ids is not None and ch.area not in area_ids:
                continue
            if not self._matches_character_selector(
                character=ch,
                owner_id=owner_id,
                spec=spec,
                alive_only=alive_only,
            ):
                continue
            targets.append(ch.character_id)
        return targets

    def _resolve_board_targets(
        self,
        *,
        state: GameState,
        owner: Any,
        spec: TargetSelector,
        location_context: AbilityLocationContext | None,
    ) -> list[str]:
        if spec.scope in {"same_area", "initial_area", "adjacent_area", "diagonal_area"} and owner is None:
            return []
        if spec.scope == "same_area":
            owner_area = self._effective_owner_area(owner, location_context)
            return [owner_area.value] if owner_area is not None else []
        if spec.scope == "initial_area":
            owner_initial_area = self._effective_owner_initial_area(owner, location_context)
            return [owner_initial_area.value] if owner_initial_area is not None else []
        if spec.scope == "any_area":
            return [area_id.value for area_id in state.board.areas]
        if spec.scope == "fixed_area":
            return [spec.area] if spec.area else []
        if owner is None:
            return []
        current_area = self._effective_owner_area(owner, location_context)
        if current_area is None:
            return []
        if spec.scope == "adjacent_area":
            if current_area == AreaId.FARAWAY:
                return []
            return [area_id.value for area_id in state.board.get_all_adjacent(current_area)]
        if spec.scope == "diagonal_area":
            if current_area == AreaId.FARAWAY:
                return []
            diagonal = state.board.get_diagonal_adjacent(current_area)
            return [diagonal.value] if diagonal is not None else []
        return []

    def _resolve_scope_area_ids(
        self,
        *,
        state: GameState,
        owner: Any,
        spec: TargetSelector,
        location_context: AbilityLocationContext | None,
    ) -> set[AreaId] | None:
        if spec.scope == "any_area":
            return None
        if owner is None:
            return set()
        if spec.scope == "same_area":
            owner_area = self._effective_owner_area(owner, location_context)
            return {owner_area} if owner_area is not None else set()
        if spec.scope == "initial_area":
            owner_initial_area = self._effective_owner_initial_area(owner, location_context)
            return {owner_initial_area} if owner_initial_area is not None else set()
        if spec.scope == "fixed_area":
            if spec.area is None:
                return set()
            try:
                return {AreaId(spec.area)}
            except ValueError:
                return set()
        owner_area = self._effective_owner_area(owner, location_context)
        if owner_area is None or owner_area == AreaId.FARAWAY:
            return set()
        if spec.scope == "adjacent_area":
            return set(state.board.get_all_adjacent(owner_area))
        if spec.scope == "diagonal_area":
            diagonal = state.board.get_diagonal_adjacent(owner_area)
            return {diagonal} if diagonal is not None else set()
        return set()

    def _matches_character_selector(
        self,
        *,
        character: Any,
        owner_id: str,
        spec: TargetSelector,
        alive_only: bool,
    ) -> bool:
        if character.is_removed():
            return False
        if spec.subject == "other_character" and character.character_id == owner_id:
            return False

        if spec.subject == "dead_character":
            if not character.is_dead():
                return False
        elif alive_only and not character.is_active():
            return False

        if spec.filters.identity_id is not None and character.identity_id != spec.filters.identity_id:
            return False
        if spec.filters.attribute is not None:
            try:
                attribute = Attribute(spec.filters.attribute)
            except ValueError:
                return False
            if attribute not in character.attributes:
                return False
        if spec.filters.limit_reached and not self._character_reached_paranoia_limit(character):
            return False
        return True

    @staticmethod
    def _character_reached_paranoia_limit(character: Any) -> bool:
        return character.tokens.paranoia >= character.paranoia_limit

    def active_traits(self, state: GameState, character_id: str) -> set[Trait]:
        """角色当前生效特性：基础特性 + 当前身份特性 + 独立派生层。"""
        return resolve_active_traits(state, character_id)

    def goodwill_should_be_ignored(self, state: GameState, character_id: str) -> bool:
        """用于主人公能力阶段：判断是否应视为无视友好。"""
        traits = self.active_traits(state, character_id)
        return (
            Trait.MUST_IGNORE_GOODWILL in traits
            or Trait.IGNORE_GOODWILL in traits
        )

    def _has_playwright_goodwill_trait(self, state: GameState, character_id: str) -> bool:
        traits = self.active_traits(state, character_id)
        return bool(traits & _PLAYWRIGHT_GOODWILL_TRAITS)

    def evaluate_condition(
        self,
        state: GameState,
        condition: Condition | None,
        *,
        owner_id: str = "",
        other_id: str = "",
        location_context: AbilityLocationContext | None = None,
    ) -> bool:
        """基础 Condition 求值；未知 condition_type 视为 False。"""
        if condition is None:
            return True

        cond_type = condition.condition_type
        params = condition.params

        if cond_type in {"all_of", "any_of"}:
            raw_items = params.get("conditions", [])
            if not isinstance(raw_items, list):
                return False
            evaluated = [
                self.evaluate_condition(
                    state,
                    self._coerce_condition(item),
                    owner_id=owner_id,
                    other_id=other_id,
                    location_context=location_context,
                )
                for item in raw_items
            ]
            return all(evaluated) if cond_type == "all_of" else any(evaluated)

        if cond_type == "is_final_day":
            return state.is_final_day

        if cond_type == "character_alive":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            target = state.characters.get(target_id)
            return bool(target is not None and target.is_active())

        if cond_type == "character_dead":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            target = state.characters.get(target_id)
            return bool(target is not None and target.is_dead())

        if cond_type == "identity_is":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            expected = str(params.get("value", ""))
            target = state.characters.get(target_id)
            return bool(target is not None and target.identity_id == expected)

        if cond_type == "original_identity_is":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            expected = str(params.get("value", ""))
            target = state.characters.get(target_id)
            return bool(target is not None and target.original_identity_id == expected)

        if cond_type == "other_identity_is":
            expected = str(params.get("value", ""))
            target = state.characters.get(other_id)
            return bool(target is not None and target.identity_id == expected)

        if cond_type == "identity_revealed":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            target = state.characters.get(target_id)
            return bool(target is not None and target.revealed)

        if cond_type == "has_trait":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            trait_name = params.get("trait")
            if not isinstance(trait_name, str):
                return False
            try:
                trait = Trait(trait_name)
            except ValueError:
                return False
            return trait in self.active_traits(state, target_id)

        if cond_type == "has_attribute":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            attr_name = params.get("attribute")
            if not isinstance(attr_name, str):
                return False
            target = state.characters.get(target_id)
            if target is None:
                return False
            try:
                attribute = Attribute(attr_name)
            except ValueError:
                return False
            return attribute in target.attributes

        if cond_type == "area_is":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            expected_area = str(params.get("value", ""))
            target = state.characters.get(target_id)
            target_area = self._effective_character_area(
                state,
                target_id,
                owner_id=owner_id,
                location_context=location_context,
            )
            return bool(target is not None and target_area is not None and target_area.value == expected_area)

        if cond_type == "token_check":
            return self._evaluate_token_check(
                state,
                params,
                owner_id=owner_id,
                other_id=other_id,
                location_context=location_context,
            )

        if cond_type == "identity_token_check":
            return self._evaluate_identity_token_check(state, params)

        if cond_type == "identity_initial_area_board_token_check":
            return self._evaluate_identity_initial_area_board_token_check(state, params)

        if cond_type == "same_area_identity_token_check":
            return self._evaluate_same_area_identity_token_check(
                state,
                params,
                owner_id=owner_id,
                location_context=location_context,
            )

        if cond_type == "same_area_count":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
                location_context=location_context,
            )
            target_area = self._effective_character_area(
                state,
                target_id,
                owner_id=owner_id,
                location_context=location_context,
            )
            if target_area is None:
                return False
            operator = str(params.get("operator", "=="))
            value = int(params.get("value", 0))
            count = len(
                [
                    character
                    for character in state.characters.values()
                    if character.is_active() and character.area == target_area
                ]
            )
            return _compare_number(count, operator, value)

        if cond_type == "loop_number_check":
            operator = str(params.get("operator", "=="))
            value = int(params.get("value", 0))
            return _compare_number(state.current_loop, operator, value)

        if cond_type == "ex_gauge_check":
            operator = str(params.get("operator", "=="))
            value = int(params.get("value", 0))
            return _compare_number(state.ex_gauge, operator, value)

        if cond_type == "module_has_ex_gauge":
            return bool(state.module_def is not None and state.module_def.has_ex_gauge)

        if cond_type == "paranoia_limit_check":
            target_id = self._resolve_target_ref(
                state,
                params.get("target", owner_id),
                owner_id=owner_id,
                other_id=other_id,
            )
            target = state.characters.get(target_id)
            if target is None:
                return False
            operator = str(params.get("operator", "=="))
            value = int(params.get("value", 0))
            return _compare_number(target.paranoia_limit, operator, value)

        if cond_type == "incident_occurred":
            incident_id = str(params.get("incident_id", ""))
            return incident_id in state.incidents_occurred_this_loop

        return False

    def _collect_identity_as_derived(
        self,
        state: GameState,
        *,
        owner_id: str,
        derived_identity_id: str,
        timing: AbilityTiming,
        ability_type: AbilityType | None,
    ) -> list[AbilityCandidate]:
        identity_def = state.identity_defs.get(derived_identity_id)
        if identity_def is None:
            return []

        result: list[AbilityCandidate] = []
        for ability in identity_def.abilities:
            if ability.timing != timing:
                continue
            if ability_type is not None and ability.ability_type != ability_type:
                continue
            if not self._evaluate_condition_for_owner_contexts(
                state,
                ability.condition,
                owner_id=owner_id,
            ):
                continue
            candidate = AbilityCandidate(
                source_kind="derived",
                source_id=owner_id,
                ability=ability,
                identity_id=derived_identity_id,
            )
            if not self.is_ability_available(state, candidate):
                continue
            result.append(candidate)
        return result

    def _collect_from_rule(
        self,
        state: GameState,
        *,
        timing: AbilityTiming,
        ability_type: AbilityType | None,
        rule_id: str,
        abilities: list[Ability],
    ) -> list[AbilityCandidate]:
        result: list[AbilityCandidate] = []
        for ability in abilities:
            if ability.timing != timing:
                continue
            if ability_type is not None and ability.ability_type != ability_type:
                continue
            if not self.evaluate_condition(state, ability.condition):
                continue
            candidate = AbilityCandidate(
                source_kind="rule",
                source_id=rule_id,
                ability=ability,
            )
            if not self.is_ability_available(state, candidate):
                continue
            result.append(candidate)
        return result

    @staticmethod
    def _goodwill_condition_for(character_id: str, slot: int) -> Condition | None:
        if character_id == "shrine_maiden" and slot == 0:
            return Condition(
                condition_type="area_is",
                params={"target": {"ref": "self"}, "value": AreaId.SHRINE.value},
            )
        return None

    @staticmethod
    def _goodwill_effects_for(character_id: str, slot: int) -> list[Effect]:
        goodwill_map: dict[tuple[str, int], list[Effect]] = {
            ("female_student", 0): [
                Effect(
                    effect_type=EffectType.REMOVE_TOKEN,
                    target={
                        "scope": "same_area",
                        "subject": "other_character",
                    },
                    token_type=TokenType.PARANOIA,
                    amount=1,
                )
            ],
            ("male_student", 0): [
                Effect(
                    effect_type=EffectType.REMOVE_TOKEN,
                    target={
                        "scope": "same_area",
                        "subject": "other_character",
                    },
                    token_type=TokenType.PARANOIA,
                    amount=1,
                )
            ],
            ("idol", 0): [
                Effect(
                    effect_type=EffectType.REMOVE_TOKEN,
                    target={
                        "scope": "same_area",
                        "subject": "other_character",
                    },
                    token_type=TokenType.PARANOIA,
                    amount=1,
                )
            ],
            ("idol", 1): [
                Effect(
                    effect_type=EffectType.PLACE_TOKEN,
                    target={
                        "scope": "same_area",
                        "subject": "other_character",
                    },
                    token_type=TokenType.GOODWILL,
                    amount=1,
                )
            ],
            ("office_worker", 0): [
                Effect(
                    effect_type=EffectType.REVEAL_IDENTITY,
                    target={"ref": "self"},
                )
            ],
            ("shrine_maiden", 0): [
                Effect(
                    effect_type=EffectType.REMOVE_TOKEN,
                    target={
                        "scope": "same_area",
                        "subject": "board",
                    },
                    token_type=TokenType.INTRIGUE,
                    amount=1,
                )
            ],
            ("shrine_maiden", 1): [
                Effect(
                    effect_type=EffectType.REVEAL_IDENTITY,
                    target={
                        "scope": "same_area",
                        "subject": "character",
                    },
                )
            ],
        }
        return list(goodwill_map.get((character_id, slot), []))

    def _evaluate_token_check(
        self,
        state: GameState,
        params: dict[str, object],
        *,
        owner_id: str,
        other_id: str = "",
        location_context: AbilityLocationContext | None = None,
    ) -> bool:
        target = self._resolve_target_ref(
            state,
            params.get("target", owner_id),
            owner_id=owner_id,
            other_id=other_id,
            location_context=location_context,
        )
        token_name = params.get("token")
        if not isinstance(token_name, str):
            return False
        try:
            token_type = TokenType(token_name)
        except ValueError:
            return False

        operator = str(params.get("operator", "=="))
        value = int(params.get("value", 0))

        amount = 0
        if target in state.characters:
            amount = state.characters[target].tokens.get(token_type)
        else:
            try:
                area_id = AreaId(target)
            except ValueError:
                return False
            board_area = state.board.areas.get(area_id)
            if board_area is None:
                return False
            amount = board_area.tokens.get(token_type)

        return _compare_number(amount, operator, value)

    def _evaluate_identity_token_check(
        self,
        state: GameState,
        params: dict[str, object],
    ) -> bool:
        identity_id = str(params.get("identity_id", ""))
        token_name = params.get("token")
        if not isinstance(token_name, str):
            return False
        try:
            token_type = TokenType(token_name)
        except ValueError:
            return False
        operator = str(params.get("operator", "=="))
        value = int(params.get("value", 0))

        for ch in state.characters.values():
            if ch.is_removed():
                continue
            if ch.identity_id != identity_id:
                continue
            if _compare_number(ch.tokens.get(token_type), operator, value):
                return True
        return False

    def _evaluate_identity_initial_area_board_token_check(
        self,
        state: GameState,
        params: dict[str, object],
    ) -> bool:
        identity_id = str(params.get("identity_id", ""))
        token_name = params.get("token")
        if not isinstance(token_name, str):
            return False
        try:
            token_type = TokenType(token_name)
        except ValueError:
            return False
        operator = str(params.get("operator", "=="))
        value = int(params.get("value", 0))

        for ch in state.characters.values():
            if ch.is_removed():
                continue
            if ch.identity_id != identity_id:
                continue
            board_area = state.board.areas.get(ch.initial_area)
            if board_area is None:
                continue
            if _compare_number(board_area.tokens.get(token_type), operator, value):
                return True
        return False

    def _evaluate_same_area_identity_token_check(
        self,
        state: GameState,
        params: dict[str, object],
        *,
        owner_id: str,
        location_context: AbilityLocationContext | None = None,
    ) -> bool:
        owner_area = self._effective_character_area(
            state,
            owner_id,
            owner_id=owner_id,
            location_context=location_context,
        )
        if owner_area is None:
            return False
        identity_id = str(params.get("identity_id", ""))
        token_name = params.get("token")
        if not isinstance(token_name, str):
            return False
        try:
            token_type = TokenType(token_name)
        except ValueError:
            return False
        operator = str(params.get("operator", "=="))
        value = int(params.get("value", 0))

        for ch in state.characters.values():
            if not ch.is_active() or ch.area != owner_area:
                continue
            if ch.identity_id != identity_id:
                continue
            if _compare_number(ch.tokens.get(token_type), operator, value):
                return True
        return False

    @staticmethod
    def _coerce_condition(raw: Any) -> Condition | None:
        if isinstance(raw, Condition):
            return raw
        if isinstance(raw, dict):
            condition_type = raw.get("condition_type")
            if isinstance(condition_type, str):
                params = raw.get("params", {})
                if isinstance(params, dict):
                    return Condition(condition_type=condition_type, params=params)
        return None

    def _resolve_target_ref(
        self,
        state: GameState,
        raw_target: object,
        *,
        owner_id: str,
        other_id: str = "",
        location_context: AbilityLocationContext | None = None,
    ) -> str:
        selector = parse_target_selector(raw_target)
        if selector.ref == "self":
            return owner_id
        if selector.ref == "other":
            return other_id
        if selector.ref == "literal":
            return selector.value or ""
        if selector.ref == "none":
            return ""
        resolved = self.resolve_targets(
            state,
            owner_id=owner_id,
            selector=raw_target,
            condition_target=other_id,
            alive_only=False,
            location_context=location_context,
        )
        return resolved[0] if len(resolved) == 1 else ""

    def _evaluate_condition_for_owner_contexts(
        self,
        state: GameState,
        condition: Condition | None,
        *,
        owner_id: str,
        other_id: str = "",
    ) -> bool:
        for location_context in self._owner_location_context_variants(state, owner_id):
            if self.evaluate_condition(
                state,
                condition,
                owner_id=owner_id,
                other_id=other_id,
                location_context=location_context,
            ):
                return True
        return False

    def _owner_location_context_variants(
        self,
        state: GameState,
        owner_id: str,
    ) -> list[AbilityLocationContext | None]:
        owner = state.characters.get(owner_id)
        if owner is None:
            return [None]
        territory_area = getattr(owner, "territory_area", None)
        if owner.character_id != "vip" or territory_area is None or territory_area == owner.area:
            return [None]
        return [
            None,
            AbilityLocationContext(
                owner_area=territory_area,
                owner_initial_area=owner.initial_area,
            ),
        ]

    @staticmethod
    def _effective_owner_area(
        owner: Any,
        location_context: AbilityLocationContext | None,
    ) -> AreaId | None:
        if owner is None:
            return None
        if location_context is not None and location_context.owner_area is not None:
            return location_context.owner_area
        return owner.area

    @staticmethod
    def _effective_owner_initial_area(
        owner: Any,
        location_context: AbilityLocationContext | None,
    ) -> AreaId | None:
        if owner is None:
            return None
        if location_context is not None and location_context.owner_initial_area is not None:
            return location_context.owner_initial_area
        return owner.initial_area

    def _effective_character_area(
        self,
        state: GameState,
        character_id: str,
        *,
        owner_id: str,
        location_context: AbilityLocationContext | None,
        use_initial_area: bool = False,
    ) -> AreaId | None:
        character = state.characters.get(character_id)
        if character is None:
            return None
        if character_id == owner_id:
            if use_initial_area:
                return self._effective_owner_initial_area(character, location_context)
            return self._effective_owner_area(character, location_context)
        return character.initial_area if use_initial_area else character.area


def _compare_number(left: int, operator: str, right: int) -> bool:
    if operator == ">=":
        return left >= right
    if operator == ">":
        return left > right
    if operator == "<=":
        return left <= right
    if operator == "<":
        return left < right
    if operator == "!=":
        return left != right
    return left == right
