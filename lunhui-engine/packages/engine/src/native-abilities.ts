import type {
  ContentCatalog,
  EffectSpec,
  GameState,
  Operation,
  ResolutionProgram,
  RuleSourceDefinition,
  Selector,
} from './model.js';
import { evaluatePersistent } from './persistent.js';

const none: Selector = { kind: 'none' };
const e = (id: string, target: Selector, operation: Operation): EffectSpec => ({
  id,
  target,
  operation,
  chooser: 'source-owner',
});
const p = (...steps: EffectSpec[][]): ResolutionProgram => ({
  segments: steps.map((effects, index) => ({ id: `step${index}`, effects })),
});
const say = (text: string, fact?: string) => e('info', none, { kind: 'announce', text, fact });

/** Compile state-dependent choices into the same serializable program as ordinary abilities. */
export function abilityProgram(
  source: RuleSourceDefinition,
  owner: string,
  state: GameState,
  catalog: ContentCatalog,
): ResolutionProgram {
  const self: Selector = { kind: 'character', id: owner };
  const same: Selector = { kind: 'characters', filter: { area: { sameAs: owner }, not: [owner] } };
  const effective = evaluatePersistent(state, catalog);
  switch (source.native) {
    case undefined:
      return structuredClone(source.program);
    case 'servant':
      return p([
        e(
          'recipient',
          { kind: 'characters', filter: { not: [owner] } },
          { kind: 'attachment', key: `served-by:${owner}` },
        ),
      ]);
    case 'big-shot':
      return p([
        e(
          'reveal',
          {
            kind: 'characters',
            filter: { area: state.script.options[`territory:${owner}`] as never, not: [owner] },
          },
          { kind: 'reveal-identity' },
        ),
      ]);
    case 'hermit':
      return p(
        [e('move', self, { kind: 'move-character', anyArea: true })],
        [
          e(
            'corpse',
            { kind: 'characters', filter: { alive: false, area: { sameAs: owner } } },
            {
              kind: 'bundle',
              operations: [
                { kind: 'resurrect' },
                {
                  kind: 'counter',
                  counter: 'goodwill',
                  amount: Number(state.script.options[`hermitX:${owner}`] ?? 0),
                },
              ],
            },
          ),
        ],
      );
    case 'scholar': {
      const program = p([e('clear', self, { kind: 'clear-counters' })]);
      if (
        ['mystery_circle', 'weird_mythology', 'another_horizon_revised'].includes(
          state.script.moduleId,
        )
      )
        program.segments.push({
          id: 'ex',
          effects: [],
          chooser: 'source-owner',
          alternatives: [
            { id: 'increase', label: 'EX+1', effects: [e('ex', none, { kind: 'ex', amount: 1 })] },
            { id: 'decrease', label: 'EX−1', effects: [e('ex', none, { kind: 'ex', amount: -1 })] },
          ],
        });
      return program;
    }
    case 'copycat': {
      const names = Object.values(state.characters)
        .filter(
          (c) =>
            c.alive &&
            c.presence === 'board' &&
            effective.characters[c.id]!.identity === effective.characters[owner]!.identity,
        )
        .map((c) => c.name);
      return p([
        say(`与${state.characters[owner]!.name}身份相同的角色：${names.join('、') || '无'}`),
      ]);
    }
    case 'class-rep': {
      const actor = state.leader;
      const cards = state.cards[actor].filter((card) => card.oncePerLoop && card.zone === 'used');
      return {
        segments: [
          {
            id: 'card',
            effects: [],
            chooser: 'leader',
            alternatives: cards.map((card) => ({
              id: card.id,
              label: card.kind,
              effects: [e('return', none, { kind: 'return-card', cardId: card.id, seat: actor })],
            })),
          },
        ],
      };
    }
    case 'police':
    case 'spirit': {
      const entries = state.script.incidents.filter(
        (entry) =>
          source.native === 'spirit' ||
          state.records.incidentHistory.some(
            (r) => r.entryId === entry.entryId && r.loop === state.clock.loop,
          ),
      );
      return {
        segments: [
          {
            id: 'reveal',
            effects: [],
            chooser: 'source-owner',
            alternatives: entries.map((entry) => ({
              id: entry.entryId,
              label: `第${entry.day}天：${entry.publicName}`,
              effects: [
                say(
                  `第${entry.day}天${entry.publicName}的当事人：${entry.crowdArea ?? entry.culpritIds.map((id) => state.characters[id]!.name).join('、')}`,
                  `culprit:${entry.entryId}`,
                ),
              ],
            })),
          },
        ],
      };
    }
    case 'informant': {
      const module = catalog.modules[state.script.moduleId]!;
      const chosen = state.script.ruleIds.filter((id) => catalog.rules?.[id]?.kind === 'x');
      return {
        segments: [
          {
            id: 'declare',
            choices: [
              {
                key: 'declared-x',
                prompt: '声明一条规则X',
                values: module.rules.filter((id) => catalog.rules?.[id]?.kind === 'x'),
                chooser: 'source-owner',
              },
            ],
            effects: [say('声明规则X：$choice:declared-x')],
          },
          {
            id: 'reveal',
            choices: [
              {
                key: 'revealed-x',
                prompt: '公开另一条实际使用的规则X',
                values: chosen,
                exclude: '$choice:declared-x',
                chooser: 'mastermind',
              },
            ],
            effects: [say('公开规则X：$choice:revealed-x', 'rule:$choice:revealed-x')],
          },
        ],
      };
    }
    case 'transfer':
      return p([e('donor', same, { kind: 'move-counter', amount: 1, to: same })]);
    case 'uploader':
      return {
        segments: [
          {
            id: 'tokens',
            effects: [
              e('recipient', same, {
                kind: 'bundle',
                operations: [
                  { kind: 'counter', counter: 'goodwill', amount: 1 },
                  { kind: 'counter', counter: 'anxiety', amount: -1 },
                ],
              }),
            ],
          },
          {
            id: 'transfer-ex',
            optional: true,
            chooser: 'source-owner',
            effects: [
              {
                ...e(
                  'next',
                  {
                    kind: 'characters',
                    filter: {
                      area: { sameAs: '$target:recipient' },
                      not: [owner, '$target:recipient'],
                    },
                  },
                  { kind: 'attachment-transfer', from: '$target:recipient', key: 'uploader-ex' },
                ),
                condition: { kind: 'attachment', target: '$target:recipient', key: 'uploader-ex' },
              },
            ],
          },
        ],
      };
    case 'sister':
      return {
        segments: [
          {
            id: 'adult',
            effects: [say('妹妹邀请同区域成人使用友好能力')],
            abilityChoice: {
              kind: 'characters',
              filter: { area: { sameAs: owner }, attribute: '成人' },
            },
          },
        ],
      };
    case 'ai':
      return {
        segments: [
          {
            id: 'event',
            effects: [],
            eventChoice: state.script.incidents.map((entry) => {
              const found = Object.values(catalog.incidents).find(
                (event) =>
                  event.name === entry.publicName &&
                  catalog.modules[state.script.moduleId]!.incidents.includes(event.id),
              );
              return found?.id ?? `no-effect:${entry.entryId}`;
            }),
          },
        ],
      };
    default:
      throw new Error(`ABILITY_HANDLER_MISSING:${source.native}`);
  }
}
