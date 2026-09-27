# v2 流程到实现映射

以用户的三份流程稿组织内核，不复用旧宿主手动推进模型。常驻是按状态派生的结果，不是持续重复发动的来源。

| 流程区域                     | 实现入口                                      | 验证入口                                  |
| ---------------------------- | --------------------------------------------- | ----------------------------------------- |
| 剧本锁定与制作限制           | state.ts、validation.ts                       | module-flow、module-boundaries            |
| 轮回复原、登场与上轮快照     | runtime.ts、native-rules.ts                   | regressions、abilities                    |
| 九阶段与玩家选择             | runtime.ts                                    | flow、module-flow                         |
| 行动牌同时移动／增加／减少   | actions.ts、resolution.ts                     | actions、module-boundaries                |
| 首步骤目标检查、拒绝与沟通   | runtime.ts、query.ts、resolution.ts           | resolution、abilities                     |
| 事件发生、条件修正、教主与AI | incidents.ts、native-incidents.ts、runtime.ts | abilities、module-boundaries、regressions |
| 同批死亡与必须后续           | resolution.ts、runtime.ts                     | resolution、regressions                   |
| 常驻身份、特性、计数及资格   | persistent.ts                                 | resolution、module-boundaries             |
| 轮回失败与胜利条件           | native-rules.ts、runtime.ts                   | module-flow、regressions                  |
| LL支线、表里身份最终推理     | runtime.ts                                    | module-boundaries                         |
| 等待恢复与秘密白名单         | checkpoint.ts、runtime.ts、contracts          | flow、module-flow、regressions            |

文件名均位于 packages/engine/src，另有说明者除外；测试位于 tests。

每批有共享读取快照和独立来源游标。所有意图准备完成才提交；状态变化后的强制子批次先收尾，再确认来源完成并触发完成后能力。已有结束要求不吞掉当前必须后续，但会截断原来源尚未开始的“随后”。轮回结束自身的清理来源不因旧结束要求被截断。

已触发强制／事件来源无目标仍处理为完成；主动能力的首步骤无合法目标则不发动。跳过可选后续不撤销前段。教主两次文本均完成后才登记事件完成；银弹在文本完成时请求结束，不直接判失败。

死亡触发保留死亡前身份与获得能力；普通完成后触发重新检查当前在场、存活、有效身份／能力和限次。明确允许尸体处理的愚者等例外单列。

客户端没有直接推进阶段、任意修改状态或注入效果的接口。旧版 beginLoopEnd／finishLoopEnd／startGoodwill 已由自动节点替代。
