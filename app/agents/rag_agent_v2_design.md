## RAG Agent V2 重构设计（对齐 common_qa 模板）

目标：在保持现有接口与调用方式不变的前提下，最大化复用 common_qa 的持久化与历史对话处理模式，消除代码冗余，修复流式输出问题（不再输出改写查询，回答结束后追加参考来源）。

### 参考基线
- 持久化与历史：复用 `common_qa` 的流程，首次调用加载 `system_prompt`，读取/写入 `chat_history`，MySQL 记录用户与助手消息，输出的最终文本写回历史。
- 图构建：参照 `common_qa.graph.build_common_qa_graph` 的简洁结构，按节点拆分，节点函数内注入依赖（llm_service、req_client）。
- 流式输出：参照 `common_qa.agent.stream` 的 `graph.astream_events` 处理方式，但按 RAG 需求补充参考来源输出。

### 状态定义（保持 V1 兼容，明确 retrieved/references）
- `raw_input`: 原始用户输入。
- `tag`: 解析出的检索标签（可为空）。
- `parsed_query`: 解析后的查询（含 tag 处理）。
- `rewritten_query`: 改写后的查询。
- `retrieved`: 检索接口原始返回的切片列表（不拼接、不改写）。
- `references`: 基于 `retrieved` 拼接后的参考来源片段（供最终展示）。
- `answer`: 模型生成的回答文本。
- `answer_source`: `kb` | `llm_fallback`。
- `metadata`: `thread_id` 等。
- 历史消息：与 `common_qa` 一致，从 Redis 取，首次对话注入 `system_prompt`。

### 节点设计
1) `parse_input_node`
   - 逻辑复用 V1：支持 `searchTagFilter:xxx, query:yyy` 与纯 query。
   - 产出：`parsed_query`, `tag`, `domain_context.last_query`。

2) `rewrite_query_node`
   - 调用现有改写提示与 LLM。
   - 仅更新状态中的 `rewritten_query`，**不向前端流式输出改写文本**。
   - 改写失败回退 `parsed_query/raw_input`。

3) `req_search_node`
   - 调用现有检索接口。
   - 将接口原样返回保存到 `retrieved`。
   - 参考来源拼接逻辑迁移到此节点：根据 `retrieved` 构造 `references`（保留现有 modal/card 格式），同时不丢失 `retrieved`。
   - 若检索报错或为空，标记可用于后续 `llm_fallback`。

4) （移除）`preprocess_results_node`
   - 删除节点与边；相关简单重组逻辑已在 `req_search_node` 完成。

5) （移除/合并）`judge_answerable_node`
   - 不再独立节点；可回答性的判断在 `compose_answer_node` 内根据 `retrieved` 是否为空完成，设置 `answer_source` 与 `fallback_reason`。

6) `compose_answer_node`
   - 若 `retrieved` 为空或检索异常 → `llm_fallback`：使用通识能力回答，不引用参考来源。
   - 若有 `retrieved` → 按原提示 `answer_with_refs.md` 生成回答。
   - 流式策略：流式输出只包含回答正文；当回答流结束后，立刻追加一次 `type="message"` 的参考来源卡片（使用状态中的 `references` 构造）。
   - 保持 `retrieved`、`references` 在最终状态中，供持久化与 metadata。

### 流式输出协议
- 回答分片：`{"type": "message", "data": <answer_chunk>}`。
- 回答完成后追加参考来源：`{"type": "message", "data": <references_part>}`，格式沿用 V1 的 modal/card 片段。
- 元数据：`{"type": "metadata", "data": {"thread_id": ..., "can_answer": ..., "answer_source": ..., "fallback_reason": ...}}`。
- 不再输出改写后的查询。

### 错误与回退
- 改写失败：使用原始/解析查询。
- 检索失败/空结果：`answer_source="llm_fallback"`，直接用模型通识回答，参考来源留空。
- 流式异常：输出 `type="error"`，日志记录。

### 持久化与历史
- 用户/助手消息写 MySQL（同 `common_qa`）。
- 历史写入：保存用户消息与最终拼接后的完整助手文本（回答 + 参考来源）；保持 `thread_id` 关联。
- 首次对话注入 `system_prompt`；`is_new_conversation` 时跳过历史查询。

### 复用与改造点
- 保留 prompts、req_client、message_formatter 现有实现。
- 图结构：`parse_input` → `rewrite_query` → `req_search` → `compose_answer` → END。
- 依赖注入：在 `build_graph` 中设置 llm_service/req_client（同 V1）。
- 将参考来源拼接逻辑集中在节点内，避免 agent 层重复代码。

### 开发任务拆分
1. 对比 `common_qa.agent`，统一 RAG agent 的持久化与历史处理（invoke/stream）。
2. 重写 `graph.py` 去除多余节点，更新边。
3. 精简 `nodes.py`：移除 preprocess/judge，调整 req_search 构造 references，compose_answer 内处理 fallback 与流式行为（不输出改写）。
4. 调整流式管线：只流回答，尾部流参考来源，保留 metadata。
5. 验证 prompts 与 req_client 兼容性；必要时轻量调整 message_formatter 仅用于非流式（如仍需）。
