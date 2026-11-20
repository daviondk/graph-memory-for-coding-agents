# Block Context Bench

Block Context bench evaluates **stale tool observations in the trajectory**, not just stale prompt text. Construction: mutate critical evidence before Agent A runs; after Agent A reads it into the trajectory, B-side restore returns the environment to the original benchmark state; scoring still uses the **original gold answer**.

---

## 1. Bench 如何搭建

### 1.1 基本对象

每道题实例包含：

| 对象 | 含义 |
|---|---|
| **original_env** | HotpotQA 原始 corpus 文本，与 gold answer 一致 |
| **evidence span** | 一条可被 Agent 读到的观测，对应 `(source_path, sentence)` |
| **patch** | 对某一 evidence span 的文本替换：`original_text → mutated_text` |
| **gold answer** | 原 benchmark 标准答案，**不因 mutation 改变** |

环境只有两个可执行状态转移：

```text
A-side（run 开始前）:  original_env  --mutate-->  mutated_env
B-side（race 触发时）: mutated_env   --restore--> original_env
```

B-side 就是 A-side 的逆操作：把 `mutated_text` 换回 `original_text`。patch 文件同时定义两侧替换，不需要 Agent B 自由发挥。

### 1.2 任务选取

以 HotpotQA 为例，从 validation split 中筛题，偏好：

- `level=hard`，多跳（≥2 个 supporting fact，来自 ≥2 篇文档）
- gold answer **不能**出现在所有 supporting sentence 里（必须存在组合推理）
- 答案非 yes/no，长度可控
- 10 篇 context 文档全部本地化，Agent 只能通过 `grep` / `read_file` 接触

### 1.3 Observation 如何选出

Observation 不是预先写死的 ReAct 轨迹，而是从 benchmark 提供的 **证据监督** 里挑 span：

**HotpotQA**：每条 `supporting_facts[i] = (title, sent_id)` 对应 corpus 中一句原文。

1. 将每篇 context 段落物化为 `corpus/original/doc_XX.json`
2. 把 `(title, sent_id)` 映射为 `source_path` + `original_text`
3. 按推理角色标注：
   - **answer_bearing**：直接承载最终答案的句子（实体、数字、日期、比较关系）
   - **bridge_only**：第一跳桥接实体，改错会把检索引向错误文档
   - **supporting**：辅助证据，增加 stale 误导面

**选取原则**：

- 优先选 Agent **必须 read** 才能拿到关键信息的 span（grep snippet 不足以答题）
- mutation 后若 Agent **仍信任旧 observation**，应得出 **错误答案**
- 同一题可有多条 patch，各自独立绑定 `race_trigger`
- 可选 **distractor patch**：改非 supporting 文档中的句子，测 Agent 是否会被无关变更干扰

每条 patch 记录：

```text
evidence_id, source_path, original_text, mutated_text, role, race_trigger
```

其中 `race_trigger = after_read:<doc_id>`，表示 Agent A **读完** 该文档后，B-side 才可针对这条 patch 恢复。

### 1.4 Patch 如何设计与修复

**Mutation 模式**（局部、可信、足够误导）：

| 类型 | 示例 |
|---|---|
| answer_bearing | 实体替换、年份/数字修改、比较关系翻转（more→less） |
| bridge_fact | 桥接人物/地点/作品名替换，使下一跳检索偏离 |
| relation_comparison | before/after、大小、地点关系改写 |

**设计约束**：

- 只改 **一个句子或句内片段**，不做全文重写（hard 扩展题除外）
- `mutated_text` 在语义上应 **plausible**，不像随机噪声
- 改完后，若 Agent 只依赖 **已读到的 mutated observation** 作答，结果应错
- B 恢复后，workspace 与 **original_env + gold answer** 再次一致

**修复 / 校验流程**（构造阶段，非 runtime）：

1. **Oracle 检查**：无 patch 跑一遍，确认模型能答对 → 排除"题本身太难"
2. **Patch 有效性检查**：有 A-side mutation、无 B restore 时，错误答案应可预期
3. **Slot 替换**：某题 no-patch 仍失败 → 换 benchmark_id，只替换该 slot
4. **Manual override**：自动 mutation 不合适时，手写 `mutated_text` 与 rationale
5. **Augment 扩展**：在 30 题 base 上，为每题加 0–2 条 unrelated distractor patch；另采样 hard multihop 题，用 **整句重写型** answer-path patch，专门测 Block Context 无法局部 repair、只能发 refresh notice 的情况

最终产物：`pioneer_augmented.json`（40 题题面 + gold + supporting 元数据）与 `patch_candidate_augmented.json`（每题 patch 列表，含 A/B 两侧替换）。

---

## 2. 评测时的行为

### 2.1 时间线

```text
t0  加载 instance，写入全部 A-side patch
    workspace ← mutated_env

t1  Agent A 开始 ReAct 循环（policy 决定如何处理 stale observation）

t2  Agent A 调用 grep / read_file
    → tool 返回当前 workspace 内容（此时仍是 mutated）
    → 返回内容注册为 source-backed mutable observation block，进入轨迹

t3  race trigger 命中（见 2.2）
    → Agent B 对相应 patch 执行 B-side restore
    → workspace ← 该 span 恢复为 original_text
    → 已写入轨迹的旧 observation **默认仍然保留**（Naive baseline）

t4  Agent A 继续推理，最终调用 answer

t5  用 **original benchmark gold answer** 判对错（与是否经历过 mutation 无关）
```

核心不变量：**判分标准始终是 original_env 下的正确答案**；B-side 的作用是把"地面真相"改回去，从而检验 Agent 是否还在用 t2 时刻读到的 stale observation。

### 2.2 B.patch 何时触发

`RaceController` 按 **tool-event 边界** 确定性触发，每个 patch 独立维护 `restored` 状态。

**触发规则 1 — read 触发（主路径）**

Agent A 执行 `read_file(path)` 返回后：

- 若 `path` 匹配某条 **未恢复** patch 的 `source_path` 或 `race_trigger` 中的 `doc_id`
- 立即对该 patch 做 B-side：`mutated_text → original_text`
- 典型场景：Agent 读完含假证据的文档后，环境悄悄恢复成真证据

**触发规则 2 — grep 未跟进 read**

Agent A 执行 `grep` 后，结果中包含若干 `path`：

- 若 **下一步 tool** 不是对这些 path 之一做 `read_file`
- 则恢复 grep 命中路径上所有未恢复的 patch
- 典型场景：Agent 只看 snippet、不 read 全文，B 仍会把相关文档改回

**触发规则 3 — 过早 answer 拦截**

Agent A 在仍有未恢复 patch 时调用 `answer`：

- **丢弃** 本次 answer，不结束 episode
- **一次性恢复** 所有剩余 patch
- Agent 从 **上一次 tool return 的 messages 状态** 重新生成（最多 3 次）
- 保证最终判分时 workspace 已是 original_env，但轨迹里可能仍留着更早的 stale observation

### 2.3 Agent A 轨迹里 observation 的角色

一次 tool call 在 Block Context 层会产生：

| Block 类型 | 内容 | 是否可变 |
|---|---|---|
| immutable | system prompt、reasoning、tool call 参数 | 否 |
| mutable (source-backed) | grep hit、read_file 返回的原文片段 | 是 |

B.patch 改的是 **workspace 源文件**，不是直接改 messages 字符串。因此：

- **Naive (`raw`)**：messages 里旧 tool result 原样保留 → 典型 stale failure
- **Alert**：B restore 后在后续 tool output 追加 `[alert] path is modified`，但不强制重读
- **Diff (`git`)**：要求 answer 前先 `diff()`，展示 mutated→original 差异
- **Block Context**：runtime 对受影响 mutable block 做 repair / omit，并在 safe context 末尾追加 refresh notice

Oracle baseline **不启用** A-side mutation，无 race，作为能力上界。

### 2.4 单题交互示例

题：比较 Nick Carter 与 Brady Seals 谁 solo 专辑更多（gold: `Brady Seals`）。

patch-1：`doc_09` 中 `"fourth solo album"` → `"second solo album"`（answer_bearing）  
patch-2：`doc_06` 中 `"three solo albums"` → `"five solo albums"`（answer_bearing）

```text
[mutated_env]  Agent: grep "solo album"
               → 返回 snippet（仍为 mutated 文本）

[mutated_env]  Agent: read_file(doc_09)
               → 返回 "second solo album..."  ← observation O1 写入轨迹
               → B.patch: doc_09 恢复为 "fourth solo album..."
               → workspace 已是 original，但 O1 仍是 "second..."

[original_env] Agent: read_file(doc_06)   （若继续读）
               → 返回 "three solo albums..."
               → B.patch: doc_06 恢复

[original_env] Agent: answer("Nick Carter")  ← 若仍信 O1，答错
               或 answer("Brady Seals")     ← 重读 / Block Context repair 后可对
```

### 2.5 判分

- **主指标**：最终 `answer` 与 **original gold answer** 的语义等价性（LLM judge 或 EM/F1）
- **不**按 mutated_env 下的"假答案"判分
- 诊断量：`resend_answer_count`（过早 answer 被拦截次数）、stale 值是否出现在最终推理、各 policy 下是否触发 reread

---

## 3. 小结

| 阶段 | 做什么 |
|---|---|
| **搭建** | 从 benchmark 证据中选出 observation span → 设计局部 mutation → 定义 A/B 成对替换 → 校验 oracle 与 patch 有效性 |
| **评测** | 先 A-side 改错 → Agent A 中途读到 stale observation → B.patch 在 read/grep/answer 边界恢复 original_env → 仍按原 gold 判分 |

Bench 隔离了 **"环境已恢复，但轨迹记忆仍过期"** 这一 failure mode；对比不同 context policy 能否在不要求 Agent 自发全量 reread 的前提下恢复正确作答。
