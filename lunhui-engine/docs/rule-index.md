# 规则基线与内容映射

2026-09-26 的逐条来源盘点、实现位置、测试证据和已确认问题见 [content-audit.md](content-audit.md)；正文与流程索引见 [content-audit-flow.md](content-audit-flow.md)。这些清单区分“已定位实现”和“专项验收通过”，不以注册数量代替完成度。

docs/rule-baseline.json 保存父目录五份源文件的 SHA-256。baseline 脚本读取 UTF-8、去 BOM、统一换行后核验；不自动接受规则改动。

当前依据：全阶段逻辑样例、事件阶段逻辑样例、步骤结算流程独立稿、游戏规则正文、附录；补充读取术语修改计划和 2026-09-22 本地 FAQ 复核报告。流程稿已明确的口径记录在 rulings.md。

## 内容层

- registry.ts：八模组 Y/X 规则、身份数量与事件目录。
- index.ts：身份／角色定义、常规事件和基础能力，导出 createCatalog 与 firstStepsScenario。
- identity-sources.ts：各身份按时点实例化的强制／任意能力。
- character-sources.ts：全部角色友好能力注册；动态选择在 native-abilities.ts 编译。
- native-incidents.ts：复杂事件按同一结算程序编译。
- native-rules.ts：模组授牌、角色特性、延迟及跨轮规则、失败条件。
- persistent.ts：一般常驻与 LL 指定阶段特殊胜利。

contentCoverage 仅检查事件名是否登记，不证明语义覆盖，不作为“全部规则完成”的判据。

## 测试映射

| 测试文件                    | 范围                                                        |
| --------------------------- | ----------------------------------------------------------- |
| actions.test.ts             | 方向合成、手牌与幻想作用范围                                |
| resolution.test.ts          | 同时结算、死亡保护、来源完成与截断、常驻胜利                |
| flow.test.ts                | 自主阶段、拒绝越席与恢复一致                                |
| abilities.test.ts           | 动态友好、AI、妹妹、临时工、诅咒与延迟禁行                  |
| module-boundaries.test.ts   | 御神木、虚拟尸体、银弹、黑猫、LL、AHR、配置与存档           |
| module-flow.test.ts         | 八模组合法配置整局与中途恢复                                |
| regressions.test.ts         | 重构中发现的跨步骤与信息边界缺陷                            |
| persistent.test.ts          | 常驻转换、资格优先级、依赖冲突、固定种子100组纯派生性质检查 |
| character-matrix.test.ts    | 46项角色友好能力的可执行性和恢复检查                        |
| incident-matrix.test.ts     | 八模组82个事件条目的可执行性和恢复检查                      |
| content-consistency.test.ts | 37张角色卡属性、门槛、限次以及模组引用与附录逐项一致        |
| protocol.test.ts            | 回执重试、非法选择不变性、本机传输和8组固定种子随机对局     |
| announcements.test.ts       | 收尾公告、未发生事件、翻牌时点和公开EX牌信息隔离            |

firstStepsScenario 为 3 轮、每轮 4 日，谋杀计划＋开膛者的魔影；五名角色和两条事件配置经过当前校验。整局演示不依赖宿主手工调用阶段。
