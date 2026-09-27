import { Engine, createGame } from '../../packages/engine/src/index.js';
import { createCatalog, firstStepsScenario } from '../../packages/content/src/index.js';
const catalog = createCatalog();
const engine = new Engine(createGame(firstStepsScenario(), catalog), catalog);
engine.start();
let commands = 0;
while (engine.waiting) {
  if (++commands > 2000) throw new Error('DEMO_LOOP_LIMIT');
  const w = engine.waiting;
  const selected = w.options.find((o) => o.id === 'finish') ?? w.options[0]!;
  const receipt = engine.submit(w.actor, {
    protocolVersion: 2,
    sessionId: 'local',
    branchId: 'main',
    commandId: `demo:${commands}`,
    expectedRevision: w.revision,
    waitingInputId: w.id,
    command: { kind: 'choose', optionIds: [selected.id] },
  });
  if (receipt.status !== 'accepted') throw new Error(JSON.stringify(receipt));
}
console.log(
  engine
    .view('protagonistA')
    .publicLog.map((e) => e.text)
    .join('\n'),
);
console.log('结果:', engine.state.result);
