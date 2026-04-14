# 惨剧轮回 — Claude 工作规范

## 代码定位与 Token 节省

修改代码时，按以下顺序定位，避免读取整个文件：

1. **精确定位**：先用 Grep 找到目标行号，再用 Read(offset, limit) 只读相关片段
2. **Grep 优先**：只需确认存在或找位置时用 Grep，不要 Read 整个文件
3. **Explore Agent**：探索性任务（理解代码结构、跨文件分析）交给 Explore subagent，避免污染主上下文
4. **小块读取**：单次 Read 控制在 50 行以内，除非必须看全貌

## 文档同步规则

每次修改代码后，同步更新 `PLAN.md`：
- 完成的任务打上 `[x]` 并加日期戳
- 未完成但有进展的任务更新状态说明

## 项目约定

- 引擎层（`engine/`）不依赖 UI 层
- Phase handler 放在 `engine/phases/phase_base.py`，按需拆分到独立文件
- 测试优先验证行为，不测实现细节
