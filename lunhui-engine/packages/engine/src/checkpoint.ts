import { createHash } from 'node:crypto';
import { z } from 'zod';
import { seatSchema } from '../../contracts/src/index.js';
import { AREAS, PHASES, type ContentCatalog } from './model.js';

export function catalogFingerprint(catalog: ContentCatalog): string {
  const ordered = (value: unknown): unknown =>
    Array.isArray(value)
      ? value.map(ordered)
      : value && typeof value === 'object'
        ? Object.fromEntries(
            Object.entries(value)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([key, child]) => [key, ordered(child)]),
          )
        : value;
  return createHash('sha256')
    .update(JSON.stringify(ordered(catalog)))
    .digest('hex');
}

const natural = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
const positive = natural.min(1);
const id = z.string().min(1);
const counters = z
  .object({
    goodwill: natural,
    anxiety: natural,
    intrigue: natural,
    hope: natural,
    despair: natural,
    guard: natural.max(1),
  })
  .strict();
const character = z
  .object({
    id,
    definitionId: id,
    name: id,
    printedIdentity: id,
    configuredIdentity: id,
    reverseIdentity: id.optional(),
    temporaryIdentity: id.nullable(),
    publicIdentity: id.nullable(),
    initialArea: z.enum(AREAS),
    area: z.enum(AREAS),
    presence: z.enum(['board', 'removed', 'not_entered']),
    alive: z.boolean(),
    counters,
    attachments: z.array(id),
    marks: z.object({ communicated: z.boolean(), died: z.boolean() }).strict(),
  })
  .strict();
const board = z
  .object(
    Object.fromEntries(
      ['hospital', 'shrine', 'city', 'school'].map((area) => [
        area,
        z.object({ intrigue: natural.max(3) }).strict(),
      ]),
    ),
  )
  .strict();
const sourceDefinition = z
  .object({
    id,
    name: id,
    kind: z.enum(['forced', 'optional', 'goodwill', 'incident', 'rule']),
    program: z
      .object({
        segments: z.array(
          z
            .object({
              id,
              effects: z.array(
                z
                  .object({
                    id,
                    target: z.object({ kind: id }).passthrough(),
                    operation: z.object({ kind: id }).passthrough(),
                  })
                  .passthrough(),
              ),
            })
            .passthrough(),
        ),
      })
      .passthrough(),
  })
  .passthrough();
const outcome = z
  .object({
    sourceId: id,
    started: z.boolean(),
    completed: z.boolean(),
    changed: z.boolean(),
    rejected: z.boolean(),
    truncated: z.boolean(),
    targets: z.array(
      z
        .object({
          effectId: id,
          status: z.enum(['has_target', 'no_target', 'not_required', 'not_checked']),
          candidates: z.array(id),
          selected: z.array(id),
        })
        .strict(),
    ),
  })
  .strict();
const result = z.object({ winners: z.array(seatSchema), reason: id }).nullable();
const state = z
  .object({
    schemaVersion: z.literal(2),
    revision: natural,
    contentVersion: id,
    status: z.enum(['ready', 'running', 'waiting', 'finished', 'faulted']),
    script: z
      .object({
        id,
        moduleId: id,
        ruleIds: z.array(id),
        loops: positive,
        daysPerLoop: positive,
        finalShowdown: z.boolean(),
        discussionRestriction: z.string().optional(),
        specialRules: z.array(z.string()).optional(),
        incidents: z.array(
          z
            .object({
              entryId: id,
              day: positive,
              incidentId: id,
              publicName: id,
              publicInfo: z.string().optional(),
              privateInfo: z.string().optional(),
              culpritIds: z.array(id),
              crowdArea: z.enum(['hospital', 'shrine', 'city', 'school']).optional(),
            })
            .strict(),
        ),
        options: z.record(
          z.union([z.string(), z.number().finite(), z.boolean(), z.array(z.string())]),
        ),
      })
      .strict(),
    clock: z
      .object({
        loop: positive,
        day: positive,
        phase: z.enum(PHASES),
        node: id,
        phaseInstance: natural,
      })
      .strict(),
    leader: seatSchema,
    board,
    characters: z.record(character),
    cards: z.record(
      z.array(
        z
          .object({
            id,
            kind: id,
            owner: seatSchema,
            oncePerLoop: z.boolean(),
            zone: z.enum(['hand', 'placed', 'used', 'excluded']),
          })
          .strict(),
      ),
    ),
    placements: z.array(
      z
        .object({
          id,
          cardId: id,
          owner: seatSchema,
          target: z.object({ kind: z.enum(['character', 'area']), id }).strict(),
          revealed: z.boolean(),
          affectedCharacterIds: z.array(id),
          effective: z.boolean(),
        })
        .strict(),
    ),
    curses: z.array(z.object({ id, kind: z.enum(['area', 'character']), targetId: id }).strict()),
    ex: natural,
    protagonistProtection: z.boolean(),
    traitors: z.array(seatSchema),
    secretLetters: z.record(z.enum(['A', 'B', 'C'])),
    records: z
      .object({
        loopFailed: z.boolean(),
        protagonistsDead: z.boolean(),
        endRequests: z.array(id),
        usage: z.record(natural),
        revealedFacts: z.array(z.string()),
        incidentHistory: z.array(
          z
            .object({
              sequence: natural,
              entryId: id,
              incidentId: id,
              publicName: id,
              culpritIds: z.array(id),
              loop: positive,
              day: positive,
              completed: z.boolean(),
              changed: z.boolean(),
              calledByAi: z.boolean(),
            })
            .strict(),
        ),
        loopIncidentEntryIds: z.array(id),
        firstIncidentDay: positive.nullable(),
        worldMovedToday: z.boolean(),
        worldMoveIncrementApplied: z.boolean(),
        exIncreasedThisLoop: z.boolean(),
        delayed: z.array(
          z
            .object({
              id,
              sourceId: id,
              due: id,
              expiresAtLoopEnd: z.boolean(),
              loop: positive.optional(),
              day: positive.optional(),
              payload: z.object({ segments: z.array(z.unknown()) }).passthrough(),
            })
            .passthrough(),
        ),
        previousLoop: z
          .object({
            loop: positive,
            characters: z.record(character),
            board,
            ex: natural,
            loopIncidentEntryIds: z.array(id),
          })
          .strict()
          .nullable(),
        sourceOutcomes: z.record(outcome),
      })
      .strict(),
    result,
    publicLog: z.array(z.object({ sequence: natural, type: id, text: z.string() }).strict()),
  })
  .strict();
const waiting = z
  .object({
    id,
    revision: natural,
    actor: seatSchema,
    kind: id,
    prompt: z.string(),
    options: z.array(
      z.object({ id, label: z.string(), description: z.string().optional() }).strict(),
    ),
    minSelections: natural,
    maxSelections: natural,
    canPass: z.boolean(),
    private: z.boolean(),
  })
  .strict()
  .nullable();
const execution = z
  .object({
    frames: z.array(
      z
        .object({
          kind: z.literal('resolution'),
          id,
          lanes: z.array(
            z
              .object({
                id,
                definition: sourceDefinition,
                ownerCharacterId: id.optional(),
                cursor: natural,
                choices: z.record(z.array(id)),
                bindings: z.record(z.string()),
                optionalAccepted: z.boolean().optional(),
                authorized: z.boolean(),
                done: z.boolean(),
                outcome,
                incidentRecord: natural.optional(),
              })
              .strict(),
          ),
          stage: z.enum(['prepare', 'aftermath', 'complete', 'advance']),
          readState: state.optional(),
          prepared: z.array(
            z
              .object({
                id,
                sourceInstanceId: id,
                effectId: id,
                targetId: id.optional(),
                operation: z.object({ kind: id }).passthrough(),
              })
              .strict(),
          ),
          prepareIndex: natural,
          cleanup: z.boolean(),
        })
        .strict(),
    ),
    waiting,
    waitingKey: id.nullable(),
    answers: z.record(z.array(id)),
    firedTriggerInstances: z.array(id),
    nextId: positive,
    receipts: z.record(
      z.object({ fingerprint: id, revision: natural, actor: seatSchema }).strict(),
    ),
    fault: z.string().nullable(),
    flowData: z.record(
      z.union([z.string(), z.number().finite(), z.boolean(), z.array(z.string())]),
    ),
    generated: z.record(sourceDefinition),
    trace: z.array(z.object({ id, type: id, data: z.unknown() }).strict()),
  })
  .strict();
const saveSchema = z
  .object({
    engineVersion: z.literal('2.0.0'),
    catalogFingerprint: id,
    sessionId: id,
    branchId: id,
    state,
    execution,
  })
  .strict();

export function parseCheckpoint(serialized: string): unknown {
  const raw: unknown = JSON.parse(serialized);
  const parsed = saveSchema.safeParse(raw);
  if (!parsed.success)
    throw new Error(`INVALID_CHECKPOINT:${parsed.error.issues[0]?.path.join('.')}`);
  const save = parsed.data;
  if (
    Boolean(save.execution.waiting) !== Boolean(save.execution.waitingKey) ||
    (save.state.status === 'waiting') !== Boolean(save.execution.waiting)
  )
    throw new Error('INVALID_WAITING_CHECKPOINT');
  if (
    save.execution.waiting &&
    (save.execution.waiting.revision !== save.state.revision ||
      save.execution.waiting.maxSelections < save.execution.waiting.minSelections)
  )
    throw new Error('INVALID_WAITING_CHECKPOINT');
  if (
    Object.entries(save.state.characters).some(([id, c]) => id !== c.id) ||
    Object.values(save.state.characters).reduce((sum, c) => sum + c.counters.guard, 0) > 1
  )
    throw new Error('INVALID_CHARACTER_CHECKPOINT');
  for (const frame of save.execution.frames)
    if (
      frame.prepareIndex > frame.lanes.length ||
      frame.lanes.some((lane) => lane.cursor >= lane.definition.program.segments.length)
    )
      throw new Error('INVALID_FRAME_CHECKPOINT');
  // Validation must not reorder object keys: iteration order is part of saved execution state.
  return raw;
}
