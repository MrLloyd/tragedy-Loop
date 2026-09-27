import { describe, it, expect } from 'vitest';
import {
  createBaseDeck,
  moveDestination,
  resolveActions,
  placeAction,
} from '../packages/engine/src/index.js';
import { fixture, character } from './fixtures.js';

describe('行动牌：拓扑、归属、受影响对象和回收', () => {
  it.each([
    ['hospital', ['move-horizontal'], 'shrine'],
    ['hospital', ['move-vertical'], 'city'],
    ['shrine', ['move-vertical'], 'school'],
    ['hospital', ['move-horizontal', 'move-horizontal'], 'shrine'],
    ['hospital', ['move-horizontal', 'move-vertical'], 'school'],
    ['hospital', ['move-diagonal', 'move-horizontal'], 'city'],
  ] as const)('%s + %j = %s', (area, moves, destination) => {
    expect(moveDestination(area, [...moves])).toBe(destination);
  });
  it('剧作家不安-1不限次；主人公不安-1限次', () => {
    expect(createBaseDeck('mastermind').find((c) => c.kind === 'anxiety-1')!.oncePerLoop).toBe(
      false,
    );
    expect(createBaseDeck('protagonistA').find((c) => c.kind === 'anxiety-1')!.oncePerLoop).toBe(
      true,
    );
  });
  it('版图非密谋牌只影响幻想，版图密谋牌同时作用于版图与幻想', () => {
    const { state, catalog } = fixture();
    state.characters.fantasy = character('fantasy', 'civilian', {
      definitionId: 'fantasy',
      area: 'hospital',
    });
    const card = state.cards.mastermind.find((c) => c.kind === 'intrigue+1')!;
    placeAction(state, catalog, 'mastermind', card.id, { kind: 'area', id: 'hospital' });
    const next = resolveActions(state, catalog).state;
    expect(next.board.hospital.intrigue).toBe(1);
    expect(next.characters.fantasy!.counters.intrigue).toBe(1);
    expect(next.characters.doctor!.counters.intrigue).toBe(0);
  });
});
