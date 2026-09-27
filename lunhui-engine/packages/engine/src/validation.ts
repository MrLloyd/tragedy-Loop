import type { ContentCatalog } from './model.js';
import type { NewGameInput } from './state.js';

export function validateConfiguration(input: NewGameInput, catalog: ContentCatalog): string[] {
  const { script, characters } = input;
  const errors: string[] = [];
  const module = catalog.modules[script.moduleId];
  if (!module) return errors;
  const board = ['hospital', 'shrine', 'city', 'school'];
  const integer = (value: unknown, low: number, high = Number.MAX_SAFE_INTEGER) =>
    typeof value === 'number' && Number.isSafeInteger(value) && value >= low && value <= high;
  if (!integer(script.loops, 1) || !integer(script.daysPerLoop, 1))
    errors.push('INVALID_GAME_DURATION');
  if (
    (script.discussionRestriction !== undefined &&
      typeof script.discussionRestriction !== 'string') ||
    (script.specialRules !== undefined &&
      (!Array.isArray(script.specialRules) ||
        script.specialRules.some((text) => typeof text !== 'string')))
  )
    errors.push('INVALID_PUBLIC_SCRIPT_METADATA');
  if (script.options.identityLimitException)
    errors.push('BLANKET_IDENTITY_LIMIT_EXCEPTION_FORBIDDEN');
  if (new Set(script.ruleIds).size !== script.ruleIds.length) errors.push('DUPLICATE_RULE');
  if (new Set(script.incidents.map((entry) => entry.entryId)).size !== script.incidents.length)
    errors.push('DUPLICATE_INCIDENT_ENTRY');
  if (new Set(characters.map((c) => c.definitionId)).size !== characters.length)
    errors.push('DUPLICATE_PRINTED_CHARACTER');
  const rules = script.ruleIds.flatMap((id) => (catalog.rules?.[id] ? [catalog.rules[id]!] : []));
  const enabled = (name: string) => rules.some((rule) => rule.name === name);
  const ruleIdentities = new Set(
    rules.flatMap((rule) => rule.roles.map((role) => role.identityId)),
  );
  const expected = new Map<string, [number, number]>();
  const variablePairs: Array<[string, string]> = [];
  for (const rule of rules) {
    const variable = rule.roles.filter((role) => ['表', '里'].includes(role.count));
    if (variable.length)
      variablePairs.push([
        variable.find((role) => role.count === '表')?.identityId ?? 'civilian',
        variable.find((role) => role.count === '里')?.identityId ?? 'civilian',
      ]);
    for (const role of rule.roles.filter((role) => !['表', '里'].includes(role.count))) {
      const range = /^(\d+)(?:-(\d+))?$/.exec(role.count);
      if (!range) {
        errors.push(`UNSUPPORTED_ROLE_COUNT:${rule.id}:${role.count}`);
        continue;
      }
      const count = expected.get(role.identityId) ?? [0, 0];
      expected.set(role.identityId, [
        count[0] + Number(range[1]),
        count[1] + Number(range[2] ?? range[1]),
      ]);
    }
  }
  if (enabled('捏造的秘密') && !ruleIdentities.has('key')) {
    const extra = script.options.fabricatedSecretIdentity;
    if (
      typeof extra !== 'string' ||
      !['killer', 'mastermind', 'causal_fragment'].includes(extra) ||
      ruleIdentities.has(extra)
    )
      errors.push('INVALID_FABRICATED_SECRET_IDENTITY');
    else expected.set(extra, [1, 1]);
  }
  const ordinary = characters.filter((c) => !['outsider', 'copycat'].includes(c.definitionId));
  const variableCards = ordinary.filter((c) => c.reverseIdentity);
  const unmatched = [...variableCards];
  for (const [front, reverse] of variablePairs) {
    const index = unmatched.findIndex(
      (c) => c.configuredIdentity === front && c.reverseIdentity === reverse,
    );
    if (index < 0) errors.push(`MISSING_VARIABLE_IDENTITY:${front}/${reverse}`);
    else unmatched.splice(index, 1);
  }
  if (unmatched.length) errors.push('UNALLOCATED_VARIABLE_IDENTITY');
  for (const [identity, [minimum, maximum]] of expected) {
    const cap = module.identityLimits?.[identity] ?? catalog.identities[identity]?.max ?? Infinity;
    const count = ordinary.filter(
      (c) => !c.reverseIdentity && c.configuredIdentity === identity,
    ).length;
    if (count < Math.min(minimum, cap) || count > Math.min(maximum, cap))
      errors.push(
        `ROLE_ALLOCATION:${identity}:${Math.min(minimum, cap)}-${Math.min(maximum, cap)}`,
      );
  }
  for (const c of characters) {
    const definition = catalog.characters[c.definitionId];
    if (!definition) continue;
    if (
      !c.id ||
      c.id.includes('@') ||
      c.id.includes(':') ||
      ['__proto__', 'constructor', 'prototype'].includes(c.id)
    )
      errors.push(`INVALID_CHARACTER_ID:${c.id}`);
    if (!definition.initialAreas.includes(c.initialArea))
      errors.push(`INVALID_INITIAL_AREA:${c.id}`);
    if (!module.identities.includes(c.configuredIdentity))
      errors.push(`IDENTITY_NOT_IN_MODULE:${c.id}`);
    if (
      c.reverseIdentity &&
      (script.moduleId !== 'another_horizon_revised' ||
        !module.identities.includes(c.reverseIdentity))
    )
      errors.push(`INVALID_REVERSE_IDENTITY:${c.id}`);
    if (c.definitionId === 'outsider') {
      if (
        c.configuredIdentity === 'civilian' ||
        ruleIdentities.has(c.configuredIdentity) ||
        c.reverseIdentity
      )
        errors.push(`INVALID_OUTSIDER_IDENTITY:${c.id}`);
    } else if (c.definitionId === 'copycat') {
      if (
        !characters.some(
          (other) =>
            other.id !== c.id &&
            other.configuredIdentity === c.configuredIdentity &&
            other.reverseIdentity === c.reverseIdentity,
        )
      )
        errors.push(`COPYCAT_WITHOUT_ORIGINAL:${c.id}`);
    } else if (
      !c.reverseIdentity &&
      c.configuredIdentity !== 'civilian' &&
      !expected.has(c.configuredIdentity)
    )
      errors.push(`UNALLOCATED_IDENTITY:${c.id}`);
    if (
      c.definitionId === 'spirit' &&
      !integer(script.options[`spiritLoop:${c.id}`], 1, script.loops)
    )
      errors.push(`SPIRIT_LOOP_REQUIRED:${c.id}`);
    if (
      c.definitionId === 'transfer_student' &&
      !integer(script.options[`transferDay:${c.id}`], 1, script.daysPerLoop)
    )
      errors.push(`TRANSFER_DAY_REQUIRED:${c.id}`);
    if (c.definitionId === 'hermit' && !integer(script.options[`hermitX:${c.id}`], 0))
      errors.push(`HERMIT_X_REQUIRED:${c.id}`);
    if (
      c.definitionId === 'big_shot' &&
      !board.includes(String(script.options[`territory:${c.id}`]))
    )
      errors.push(`TERRITORY_REQUIRED:${c.id}`);
    if (Object.values(c.counters).some((count) => !integer(count, 0)))
      errors.push(`INVALID_COUNTER:${c.id}`);
    if (!c.reverseIdentity) {
      const attributes = definition.attributes;
      const identity = catalog.identities[c.configuredIdentity];
      if (c.definitionId === 'ai' && c.configuredIdentity === 'civilian')
        errors.push(`AI_CANNOT_BE_CIVILIAN:${c.id}`);
      if (
        c.definitionId === 'sister' &&
        identity?.traits.some((trait) => trait.includes('ignore-goodwill'))
      )
        errors.push(`SISTER_IGNORE_GOODWILL_IDENTITY:${c.id}`);
      const scheduled = script.incidents.some((entry) => entry.culpritIds.includes(c.id));
      if (
        ['obstinate', 'fool', 'twins', 'sacrifice', 'eccentric'].includes(c.configuredIdentity) &&
        !scheduled
      )
        errors.push(`IDENTITY_REQUIRES_INCIDENT:${c.id}`);
      if (c.configuredIdentity === 'detective' && scheduled)
        errors.push(`DETECTIVE_CANNOT_BE_CULPRIT:${c.id}`);
      if (
        c.configuredIdentity === 'ninja' &&
        enabled('男子汉的战争') &&
        !attributes.includes('男性')
      )
        errors.push(`NINJA_REQUIRES_MALE:${c.id}`);
      if (
        ((['和我签订契约吧！', '少女大危机', '叛逆的世界'].some(enabled) &&
          c.configuredIdentity === 'key_person') ||
          (enabled('叛逆的世界') && c.configuredIdentity === 'causal_fragment') ||
          c.configuredIdentity === 'alice') &&
        !attributes.includes('少女')
      )
        errors.push(`IDENTITY_REQUIRES_GIRL:${c.id}`);
    }
  }
  const alreadyCulprit = new Set<string>();
  for (const entry of script.incidents) {
    const incident = catalog.incidents[entry.incidentId];
    if (!incident) {
      errors.push(`INCIDENT_HANDLER_MISSING:${entry.incidentId}`);
      continue;
    }
    if (!integer(entry.day, 1, script.daysPerLoop))
      errors.push(`INVALID_INCIDENT_DAY:${entry.entryId}`);
    if (incident.crowd) {
      if (!board.includes(entry.crowdArea ?? '') || entry.culpritIds.length)
        errors.push(`INVALID_CROWD_CONFIGURATION:${entry.entryId}`);
    } else if (entry.culpritIds.length !== 1 || entry.crowdArea)
      errors.push(`INVALID_CULPRIT_COUNT:${entry.entryId}`);
    if (!entry.publicName.trim()) errors.push(`PUBLIC_EVENT_NAME_REQUIRED:${entry.entryId}`);
    if (
      (entry.publicInfo !== undefined && typeof entry.publicInfo !== 'string') ||
      (entry.privateInfo !== undefined && typeof entry.privateInfo !== 'string')
    )
      errors.push(`INVALID_EVENT_INFORMATION:${entry.entryId}`);
    for (const id of entry.culpritIds) {
      const culprit = characters.find((c) => c.id === id);
      if (!culprit) continue;
      if (
        culprit.definitionId === 'transfer_student' &&
        Number(script.options[`transferDay:${id}`]) > entry.day
      )
        errors.push(`CULPRIT_NOT_ENTERED:${entry.entryId}`);
      const key = `${id}:${entry.incidentId}`;
      if (alreadyCulprit.has(key) && entry.incidentId !== 'serial_murder')
        errors.push(`REPEATED_CULPRIT:${id}`);
      alreadyCulprit.add(key);
    }
  }
  if (enabled('灭亡讴歌') && !script.incidents.some((entry) => entry.incidentId === 'suicide'))
    errors.push('DOOM_CHANT_REQUIRES_SUICIDE');
  if (enabled('疯狂的真相') && !characters.some((c) => c.definitionId === 'informant'))
    errors.push('CRAZY_TRUTH_REQUIRES_INFORMANT');
  if (enabled('疯狂的真相')) {
    const replacement = script.options.crazyTruthRuleY;
    if (
      typeof replacement !== 'string' ||
      !module.rules.includes(replacement) ||
      catalog.rules?.[replacement]?.kind !== 'y' ||
      script.ruleIds.includes(replacement)
    )
      errors.push('CRAZY_TRUTH_RULE_Y_REQUIRED');
  }
  if (enabled('高贵的血族')) {
    const key = characters.find(
      (c) =>
        c.configuredIdentity === 'key_person' && !['outsider', 'copycat'].includes(c.definitionId),
    );
    const vampire = characters.find(
      (c) =>
        c.configuredIdentity === 'vampire' && !['outsider', 'copycat'].includes(c.definitionId),
    );
    const sexes = (c: typeof key) =>
      catalog.characters[c?.definitionId ?? '']?.attributes.flatMap((attribute) =>
        ['男性', '少年'].includes(attribute)
          ? ['male']
          : ['女性', '少女'].includes(attribute)
            ? ['female']
            : [],
      ) ?? [];
    if (!sexes(key).some((sex) => sexes(vampire).some((other) => sex !== other)))
      errors.push('VAMPIRE_KEY_OPPOSITE_SEX_REQUIRED');
  }
  return errors;
}
