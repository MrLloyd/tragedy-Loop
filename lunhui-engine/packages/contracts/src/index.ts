import { z } from 'zod';

export const seatSchema = z.enum(['mastermind', 'protagonistA', 'protagonistB', 'protagonistC']);
export type SeatId = z.infer<typeof seatSchema>;

export const protagonistSeats = [
  'protagonistA',
  'protagonistB',
  'protagonistC',
] as const satisfies readonly SeatId[];

export const choiceSchema = z
  .object({
    protocolVersion: z.literal(2),
    sessionId: z.string().min(1),
    branchId: z.string().min(1),
    commandId: z.string().min(1),
    expectedRevision: z.number().int().nonnegative(),
    waitingInputId: z.string().min(1),
    command: z
      .object({
        kind: z.literal('choose'),
        optionIds: z.array(z.string().min(1)),
      })
      .strict(),
  })
  .strict();
export type CommandEnvelope = z.infer<typeof choiceSchema>;

export type WaitingKind =
  | 'leader'
  | 'yes_no'
  | 'action_card'
  | 'action_target'
  | 'ability'
  | 'targets'
  | 'option'
  | 'identity_guess'
  | 'incident_culprit_guess';

export interface WaitingOption {
  id: string;
  label: string;
  description?: string;
}

export interface WaitingInput {
  id: string;
  revision: number;
  actor: SeatId;
  kind: WaitingKind;
  prompt: string;
  options: WaitingOption[];
  minSelections: number;
  maxSelections: number;
  canPass: boolean;
  private: boolean;
}

export type Receipt =
  | { status: 'accepted'; revision: number }
  | {
      status: 'rejected';
      revision: number;
      code:
        | 'INVALID_INPUT'
        | 'WRONG_SESSION'
        | 'STALE'
        | 'NOT_ALLOWED'
        | 'INVALID_OPTION'
        | 'ID_REUSED'
        | 'ENGINE_ERROR';
    };

export interface VisibleCharacter {
  id: string;
  definitionId: string;
  name: string;
  area: string;
  alive: boolean;
  presence: string;
  counters: Record<string, number>;
  identity?: string;
  publicIdentity?: string;
  marks: string[];
  exCard: boolean;
}

export interface VisibleSessionSnapshot {
  sessionId: string;
  branchId: string;
  revision: number;
  status: 'ready' | 'running' | 'waiting' | 'finished' | 'faulted';
  phase: string;
  node: string;
  loop: number;
  day: number;
  leader: SeatId;
  publicScript: {
    moduleId: string;
    loops: number;
    daysPerLoop: number;
    finalShowdown: boolean;
    discussionRestriction: string;
    specialRules: string[];
    incidents: Array<{ day: number; name: string; publicInfo?: string }>;
  };
  characters: VisibleCharacter[];
  board: Record<string, { intrigue: number }>;
  ex: number;
  curses: Array<{ id: string; kind: 'area' | 'character'; targetId: string }>;
  territories: Array<{ characterId: string; area: string }>;
  secretLetter?: 'A' | 'B' | 'C';
  hand: Array<{ id: string; kind: string; zone: string }>;
  placements: Array<{
    id: string;
    owner: SeatId;
    target: { kind: 'character' | 'area'; id: string };
    cardKind?: string;
  }>;
  waiting: WaitingInput | null;
  result: null | { winners: SeatId[]; reason: string };
  publicLog: Array<{ sequence: number; type: string; text: string }>;
}

export interface GameTransport {
  getSnapshot(): Promise<VisibleSessionSnapshot>;
  submit(command: CommandEnvelope): Promise<Receipt>;
  subscribe(listener: (snapshot: VisibleSessionSnapshot) => void): () => void;
}
