# MVP2 Task Breakdown

本文件把 MVP2 拆成可以逐步实现的任务。

## 0. Documentation And Scope

- [x] 确认 MVP2 Core 范围：Step Result + Risk Rules + Preview / Confirm + 基础 eval。
- [x] 明确 AI 自动纠错作为 MVP2 Stretch / MVP2.1。
- [x] 明确向量数据库作为 MVP3。
- [x] 更新 demo 场景，加入异常、确认和纠错案例。
- [x] 定义 MVP2 pass criteria。
- [x] 记录 MVP1 中发现的失败案例。

## 1. Step Result Standardization

- [x] 定义标准化 Step Result schema。
- [x] 定义 Step Issue schema，区分 warning 和 error。
- [x] 为每个 step 记录 input row count 和 output row count。
- [x] 为每个 step 记录 input column count 和 output column count。
- [x] 为可计算的 step 记录 match rate 或 affected rate。
- [x] 为每个 step 返回 step preview。
- [x] 保留简短 message，供 UI 和 explainer 使用。

## 2. Workflow Risk Rules

- [x] 实现 missing columns 检测。
- [x] 实现 no rows matched warning。
- [x] 实现 affects most rows warning。
- [x] 实现 empty output warning。
- [x] 为每条规则定义稳定 issue code。
- [x] 为每条规则添加单元测试。
- [x] 确认 warning 不会直接阻止 workflow 执行。
- [x] 确认 error 会阻止 workflow 执行。

## 3. Backend Preview Flow

- [x] 设计 workflow preview response。
- [x] 新增 preview-only 执行流程。
- [x] 确保 preview 不调用 result explainer。
- [x] 确保 preview 使用 validator 和 risk rules。
- [x] 返回 planned workflow、step results、warnings 和 errors。
- [x] 为 preview API 添加集成测试。

## 4. Backend Confirm Flow

- [ ] 设计 confirmed workflow execute request。
- [ ] 确认用户提交的是已检查过的 workflow JSON。
- [ ] Confirm 后执行完整 workflow。
- [ ] Confirm 后调用 result explainer。
- [ ] 在 response 中保留 step results 和 final execution result。
- [ ] 为 confirm flow 添加集成测试。

## 5. Frontend Preview And Confirm UI

- [ ] 更新 frontend types，支持 Step Result 和 Step Issue。
- [ ] 在 workflow viewer 中展示每一步 status。
- [ ] 在 workflow viewer 中展示 warning 和 error。
- [ ] 在 result area 中展示 step preview。
- [ ] 有 warning 时显示 confirm action。
- [ ] 有 error 时阻止执行并显示修复提示。
- [ ] Confirm 后展示最终结果和 explanation。

## 6. MVP2 Stretch: Minimal AI Correction

- [ ] 定义 correction request 和 response schema。
- [ ] 定义 correction issue codes。
- [ ] 实现 missing column correction。
- [ ] 为 missing column correction 提供候选列。
- [ ] 实现 empty result suggestion。
- [ ] 确保 corrector 输出重新经过 validator。
- [ ] 确保 corrector 输出重新经过 preview。
- [ ] 前端展示 original workflow 和 suggested workflow。
- [ ] 用户确认 suggested workflow 后再执行。

## 7. MVP3 Prep: RAG Preparation

- [ ] 整理 transformation docs，确保每个 transformation 有清晰参数说明。
- [ ] 新增失败案例文档。
- [ ] 新增纠错案例文档。
- [ ] 保持 retrieval debug 可 inspect。
- [ ] 准备 5-10 个 retrieval evaluation queries。
- [ ] 比较 keyword retrieval 的命中质量。
- [ ] 为后续 vector retrieval 预留 service interface。

## 8. Testing And Evaluation

- [ ] 测试正常 workflow 的 step results。
- [ ] 测试 filter rows 0 命中场景。
- [ ] 测试 filter rows 影响大多数行场景。
- [ ] 测试 output row count 为 0 的场景。
- [ ] 测试 missing column error 场景。
- [ ] 测试 preview 不生成 explanation。
- [ ] 测试 confirm 后生成 explanation。
- [ ] 测试有 warning 的 workflow 不会静默生成最终 explanation。
- [ ] 手动验证 MVP2 demo scenarios。

## 9. Demo And Portfolio Polish

- [ ] 准备包含异常场景的 sample CSV。
- [ ] 准备 3 个可靠性 demo questions。
- [ ] 准备 1-2 个纠错 suggestion demo questions（Stretch）。
- [ ] 记录 before / after 对比。
- [ ] 整理 MVP2 简历描述。
- [ ] 整理项目讲解脚本。

