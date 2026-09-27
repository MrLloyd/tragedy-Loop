import type {
  CommandEnvelope,
  GameTransport,
  Receipt,
  SeatId,
  VisibleSessionSnapshot,
} from '../../contracts/src/index.js';
import { Engine } from '../../engine/src/runtime.js';

// Host-side adapter. No socket or credential handling is claimed in P1/P2.
export class LocalTransport implements GameTransport {
  private queue: Promise<unknown> = Promise.resolve();
  private listeners = new Set<(s: VisibleSessionSnapshot) => void>();
  constructor(
    private readonly engine: Engine,
    private readonly seat: SeatId,
  ) {}
  async getSnapshot(): Promise<VisibleSessionSnapshot> {
    return this.engine.view(this.seat);
  }
  submit(command: CommandEnvelope): Promise<Receipt> {
    const operation = this.queue.then(() => {
      const result = this.engine.submit(this.seat, command);
      if (result.status === 'accepted')
        for (const listener of this.listeners) {
          try {
            listener(this.engine.view(this.seat));
          } catch {
            /* observer cannot roll back a committed command */
          }
        }
      return result;
    });
    this.queue = operation.catch(() => undefined);
    return operation;
  }
  subscribe(listener: (s: VisibleSessionSnapshot) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
}
