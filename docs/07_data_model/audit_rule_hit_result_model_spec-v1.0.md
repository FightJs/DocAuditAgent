# 审核规则、命中项与审核结果数据模型规范 v1.0

- 文档目的：定义 DocAuditAgent 文档审核链路中「规则定义 → 规则命中（Finding）→ 解释与证据 → 修改建议 → 原文定位 → 审核结果汇总」的权威数据契约，作为后端持久化模型与前端结果页/证据侧栏的共同输入输出规范。
- 版本：v1.0
- 日期：2026-08-04
- 上游输入：
  - `docs/03_business_problem_modeling/document_audit_business_model.md`
  - `docs/01_business_research/contract_legal_audit_skeptical_review.md`
  - `docs/02_competitive_analysis/document-audit-results-presentation-research.md`
  - `docs/06_system_architecture/langchain_hitl_document_audit_arch-v1.0.md`
  - `docs/06_system_architecture/frontend_backend_boundary_spec-v1.0.md`
  - 本文件 v1.0 前一版本（本轮为规范化重写）
- 下游消费方：Lead 汇总规范 `docs/06_architecture_design/data_model_spec-v1.0.md`、`docs/08_api_spec/`、前端结果页与证据阅读器实现、后端审核编排与持久化实现、集成测试用例设计。
- 本阶段边界：只输出数据模型规范。不定义数据库 DDL、接口路径、提示词、前后端代码。文中 JSON 片段仅用于说明结构。

## 1. 通用约定

| 项目 | 约定 |
| --- | --- |
| 标识符 | 所有 `*_id` 为不透明字符串（实现建议 UUID）。客户端不得解析其结构或自行生成权威 ID。 |
| 时间字段 | 统一以 `*_at` 结尾，UTC ISO-8601，例如 `2026-08-04T08:30:00Z`。 |
| 枚举值 | 统一大写下划线，例如 `SEVERITY_HIGH`、`CONFIRMED`、`CHECK_LLM`。服务端只可新增枚举值；前端遇未知值必须保留原值并降级展示为「未知/待确认」，不得推断业务结论。 |
| 版本语义 | `rule_version`、`ruleset_version`、`prompt_version`、`model_name` 为不可变业务版本标识；`revision` 为乐观并发控制整数，二者不可互换。 |
| 不可变性 | Finding 的原始判据（规则引用、证据、置信度、模型版本）不可原地修改。改判通过人工决定与状态投影表达，重审通过新 `task_id` 下的新 Finding 表达。 |
| 空值语义 | 空数组表示「该维度无限制/无内容」，`null` 表示「未知或不适用」。二者不可混用；前端不得把空证据渲染为「已核实」。 |
| 权限过滤 | 标注「前端必须展示」的字段，仍须由后端按角色与案件授权过滤后返回；被过滤字段不得以 `null` 泄露存在性。 |

## 2. 实体清单

本主题共 8 个实体：`RuleSet`、`Rule`、`RuleEvaluation`、`Finding`、`FindingExplanation`、`Suggestion`、`Locator`、`AuditResult`。

### 2.1 RuleSet（规则集）

规则集是一次审核运行所固定引用的规则基线，等价于业务模型中的「审核基线」。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `ruleset_id` | string | 是 | 不透明 ID | 规则集标识。 |
| `ruleset_key` | string | 是 | 稳定业务键 | 跨版本追溯同一规则集，如 `NDA_STANDARD`。 |
| `ruleset_version` | string | 是 | 语义化版本串 | 规则集内容版本，发布后不可变。 |
| `name` | string | 是 | 自由文本 | 人可读规则集名称。 |
| `applicable_doc_types` | string[] | 是（可为空） | 受控词表，如 `NDA`、`PROCUREMENT`、`SERVICE_AGREEMENT` | 适用文档类型；空数组表示不限制。 |
| `applicable_jurisdictions` | string[] | 是（可为空） | ISO 3166 或内部法域码 | 适用法域。 |
| `languages` | string[] | 是（可为空） | BCP 47 | 适用语言。 |
| `ruleset_status` | enum | 是 | `DRAFT`、`ACTIVE`、`RETIRED`、`SUPERSEDED` | 生命周期状态。审核运行只能引用创建时为 `ACTIVE` 的快照。 |
| `rule_ids` | string[] | 是 | 至少 1 项 | 该版本包含的规则版本引用。 |
| `confidence_thresholds` | object | 是 | 见第 4 节 | 数值置信度到分档的版本化映射。 |
| `effective_at` | timestamp | 是 | UTC ISO-8601 | 生效时间。 |
| `retired_at` | timestamp | 否 | UTC ISO-8601 或 null | 停用时间；历史运行仍可引用。 |
| `published_by` | string | 是 | 用户/主体 ID | 发布责任人，用于治理留痕。 |

规则集是发布即冻结的对象。策略负责人修改内容必须产出新的 `ruleset_version`，不得静默改写已被历史审核运行引用的版本。

### 2.2 Rule（规则定义）

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `rule_id` | string | 是 | 不透明 ID | 规则版本标识（同一规则的不同版本是不同 `rule_id`）。 |
| `rule_key` | string | 是 | 稳定业务键 | 跨版本追溯同一规则，如 `LIABILITY_CAP_MISSING`。 |
| `rule_version` | string | 是 | 语义化版本串 | 规则内容版本。 |
| `ruleset_id` | string | 是 | 外键至 `RuleSet` | 所属规则集版本。 |
| `title` | string | 是 | 自由文本 | 人可读规则名称，用于前端展示。 |
| `description` | string | 是 | 自由文本 | 规则要求或禁止条件的业务摘要（面向审核者，不含实现细节）。 |
| `category` | string | 是 | 受控词表，如 `CONFIDENTIALITY`、`LIABILITY`、`TERMINATION`、`DATA_PRIVACY` | 业务风险类别，前端分组与筛选依据。 |
| `check_type` | enum | 是 | `CHECK_DETERMINISTIC`、`CHECK_LLM`、`CHECK_HYBRID` | 检查类型：确定性校验 / LLM 判断 / 混合。决定 Finding 必须携带哪些溯源字段（见第 4 节）。 |
| `rule_kind` | enum | 是 | `REQUIRED_CLAUSE`、`PROHIBITED_CLAUSE`、`THRESHOLD`、`COMPARISON`、`CONDITIONAL_OBLIGATION`、`REDLINE`、`GUIDANCE` | 规则判断方式。`GUIDANCE` 仅辅助说明，不能单独构成放行依据。 |
| `severity_default` | enum | 是 | `SEVERITY_CRITICAL`、`SEVERITY_HIGH`、`SEVERITY_MEDIUM`、`SEVERITY_LOW`、`SEVERITY_INFO` | 触发时的默认严重级别。 |
| `is_redline` | boolean | 是 | true / false | 是否红线规则；`true` 时禁止自动放行。 |
| `applicable_doc_types` | string[] | 是（可为空） | 同 RuleSet | 规则级适用文档类型；为空则继承规则集。 |
| `applicable_scopes` | string[] | 是（可为空） | 受控词表 | 适用审核范围（如交易金额区间、业务线）。 |
| `human_review_requirement` | enum | 是 | `REVIEW_REQUIRED`、`REVIEW_RECOMMENDED`、`REVIEW_NOT_REQUIRED` | 默认人工复核要求。 |
| `auto_fixable_default` | boolean | 是 | true / false | 该规则命中是否原则上可生成可自动应用的修改建议。 |
| `authority_refs` | object[] | 是（可为空） | 见下 | 条款库、模板、政策或外部依据的版本化引用。 |
| `rule_status` | enum | 是 | `ACTIVE`、`RETIRED`、`SUPERSEDED` | 规则生命周期。 |
| `prompt_version` | string | 否 | 版本串或 null | `CHECK_LLM` / `CHECK_HYBRID` 必填：该规则使用的提示模板版本。 |
| `created_at` | timestamp | 是 | UTC ISO-8601 | 规则版本创建时间。 |
| `effective_at` | timestamp | 是 | UTC ISO-8601 | 生效时间。 |

`authority_refs` 每项结构：`{ "authority_ref_id", "source_type", "source_key", "version", "citation", "excerpt", "applicability_note" }`，其中 `source_type` ∈ `TEMPLATE`、`CLAUSE_LIBRARY`、`POLICY`、`REDLINE_CATALOG`、`EXTERNAL_AUTHORITY`。依据缺失（空数组）时，由该规则产生的 Finding 必须在解释中标注「依据不足」并强制人工复核。

规则内部执行配置（阈值公式、检索查询、正则、提示词正文）默认不返回给前端；后端必须存储受控快照以支持结论复现。

### 2.3 RuleEvaluation（规则评估记录）

记录「某条规则在某次审核任务中是否适用、是否执行成功」。它与 Finding 分离，避免用「没有命中」错误表达「规则未执行」。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `evaluation_id` | string | 是 | 不透明 ID | 评估记录标识。 |
| `task_id` | string | 是 | 外键（Teammate 1 定义） | 所属审核任务/运行。 |
| `document_id` | string | 是 | 外键（Teammate 1 定义） | 被审文档版本。 |
| `rule_id` | string | 是 | 外键至 `Rule` | 被评估的规则版本。 |
| `rule_version` | string | 是 | 版本串 | 冗余落库的规则版本，便于审计查询。 |
| `ruleset_id` | string | 是 | 外键至 `RuleSet` | 所用规则集版本。 |
| `evaluation_status` | enum | 是 | `NOT_APPLICABLE`、`EVALUATED`、`INCONCLUSIVE`、`FAILED`、`SKIPPED` | 执行事实。`FAILED` / `SKIPPED` / `INCONCLUSIVE` 不等于「未命中」，也不等于「无风险」。 |
| `applicability_reason` | string | 是 | 自由文本 | 适用、不适用或无法判断的可读理由。 |
| `finding_ids` | string[] | 是（可为空） | 外键至 `Finding` | 本次评估产出的命中项。 |
| `failure_summary` | string | 否 | 自由文本或 null | 安全、可行动的失败摘要（不含内部堆栈或凭据）。 |
| `started_at` | timestamp | 是 | UTC ISO-8601 | 评估开始时间。 |
| `completed_at` | timestamp | 否 | UTC ISO-8601 或 null | 评估完成时间。 |

### 2.4 Finding（命中项 / 发现）

Finding 是可被人工独立处置的候选风险项，主键 `finding_id`。它不是批准，也不是法律意见。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `finding_id` | string | 是 | 不透明 ID，主键 | 命中项标识，全局唯一，跨主题引用键。 |
| `task_id` | string | 是 | 外键（Teammate 1） | 所属审核任务；固定不可改。 |
| `document_id` | string | 是 | 外键（Teammate 1） | 被审文档版本；固定不可改。 |
| `evaluation_id` | string | 是 | 外键至 `RuleEvaluation` | 来源规则评估。 |
| `rule_id` | string | 是 | 外键至 `Rule` | 命中的规则版本。 |
| `rule_version` | string | 是 | 版本串 | 落库冗余的规则版本（审计必需）。 |
| `ruleset_id` | string | 是 | 外键至 `RuleSet` | 所用规则集版本。 |
| `ruleset_version` | string | 是 | 版本串 | 落库冗余的规则集版本。 |
| `hit_type` | enum | 是 | `MATCHED`、`MISSING`、`DEVIATION`、`CONFLICT`、`THRESHOLD_BREACH`、`EVIDENCE_GAP` | 命中表达的偏离类型或证据缺口。 |
| `category` | string | 是 | 同 `Rule.category` | 业务风险类别，用于列表分组。 |
| `title` | string | 是 | 自由文本，建议 ≤ 80 字符 | 一眼可判的风险标题。 |
| `summary` | string | 是 | 自由文本 | 简短结论说明，不含模型思维链。 |
| `severity` | enum | 是 | `SEVERITY_CRITICAL` / `_HIGH` / `_MEDIUM` / `_LOW` / `_INFO` | 本命中的实际严重级别，可覆盖规则默认值。 |
| `is_redline` | boolean | 是 | true / false | 是否由红线规则触发。 |
| `confidence_score` | number | 是 | 闭区间 [0, 1]，两位小数 | 数值置信度（系统判据）。 |
| `confidence_band` | enum | 是 | `CONFIDENCE_HIGH`、`CONFIDENCE_MEDIUM`、`CONFIDENCE_LOW`、`CONFIDENCE_UNKNOWN` | 展示与路由用的置信度分档，由规则集阈值映射得出。 |
| `human_review_requirement` | enum | 是 | 同 `Rule` | 本命中的人工复核要求（可被分流规则上调，不可下调）。 |
| `finding_status` | enum | 是 | 见第 5 节状态表 | 处置状态投影，由后端依据人工决定推导，前端与人工提交不得直写。 |
| `locator_ids` | string[] | 是（可为空） | 外键至 `Locator` | 支持该命中的原文定位；为空必须展示「证据不足」。 |
| `explanation_id` | string | 是 | 外键至 `FindingExplanation`，1:1 | 解释性记录。 |
| `suggestion_ids` | string[] | 是（可为空） | 外键至 `Suggestion` | 修改建议集合。 |
| `cluster_key` | string | 否 | 稳定哈希或 null | 风险簇键：同一原文范围触发多规则时用于前端聚合展示，不合并 `finding_id`。 |
| `decision_id` | string | 否 | 外键（Teammate 3），可空 | 当前生效的人工决定引用；无人工处置时为 null。 |
| `superseded_by_finding_id` | string | 否 | 外键至 `Finding` 或 null | 重审后对应的新命中项，历史不删除。 |
| `revision` | integer | 是 | ≥ 0 | 乐观并发版本，人工提交处置时必须回传。 |
| `created_at` | timestamp | 是 | UTC ISO-8601 | 命中生成时间。 |
| `updated_at` | timestamp | 是 | UTC ISO-8601 | 状态投影最近更新时间。 |

### 2.5 FindingExplanation（解释性字段：为什么命中）

每个 Finding 必须有且仅有一条解释记录，1:1。它同时承载「给人看的解释」和「给系统用的溯源判据」，两类字段在第 4 节明确区分。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `explanation_id` | string | 是 | 不透明 ID | 解释记录标识。 |
| `finding_id` | string | 是 | 外键至 `Finding`，唯一 | 被解释的命中项。 |
| `reason_text` | string | 是 | 自由文本 | 人可读理由：为什么该条款构成风险。禁止包含模型逐步推理、隐藏提示、凭据。 |
| `reason_codes` | string[] | 是（可为空） | 受控词表，如 `CLAUSE_ABSENT`、`CAP_BELOW_THRESHOLD`、`TERM_CONFLICT` | 可审计、可统计的结构化原因码。 |
| `evidence_refs` | object[] | 是（可为空） | 见下 | 证据引用：把结论绑定到具体原文 span 与依据。 |
| `evidence_summary` | string | 是 | 自由文本 | 证据与规则要求之间的关联摘要。 |
| `authority_ref_ids` | string[] | 是（可为空） | 引用 `Rule.authority_refs` | 本次判断实际引用的依据；为空必须标注「依据不足」。 |
| `extracted_values` | object | 否 | JSON object 或 null | 结构化提取值，如 `{"liability_cap": {"amount": 100000, "currency": "CNY"}}`，供审核者核对。 |
| `counter_evidence` | string | 否 | 自由文本或 null | 反证或可能推翻结论的上下文（例如别处存在例外约定）。 |
| `limitations` | string[] | 是（可为空） | 受控词表 + 说明文本 | 已知限制，如 `OCR_LOW_QUALITY`、`ATTACHMENT_MISSING`、`TRUNCATED_INPUT`、`JURISDICTION_UNVERIFIED`。 |
| `generated_by` | enum | 是 | `SYSTEM_RULE`、`LLM_AGENT`、`HYBRID` | 解释产生主体。必须与 `Rule.check_type` 一致。 |
| `model_name` | string | 否 | 模型标识串 | `LLM_AGENT` / `HYBRID` 必填：产出该判断的模型名。 |
| `model_version` | string | 否 | 版本串 | `LLM_AGENT` / `HYBRID` 必填：模型版本或快照标识。 |
| `prompt_version` | string | 否 | 版本串 | `LLM_AGENT` / `HYBRID` 必填：提示模板版本。 |
| `retrieval_refs` | object[] | 是（可为空） | `{ "query", "source_key", "source_version", "retrieved_at" }` | 检索溯源：本次判断使用的检索查询与命中来源版本。 |
| `auto_fixable` | boolean | 是 | true / false | 本命中是否可由建议自动修复（结合规则默认值与证据质量判定）。 |
| `generated_at` | timestamp | 是 | UTC ISO-8601 | 解释生成时间。 |

`evidence_refs` 每项结构：

```json
{
  "locator_id": "loc_7f3a",
  "quote": "本协议下任一方的累计责任不超过人民币十万元",
  "role": "PRIMARY_SPAN",
  "content_hash": "sha256:9c1e…"
}
```

`role` ∈ `PRIMARY_SPAN`（规则直接命中的文本）、`CONTEXT_SPAN`（判断所依赖的上下文）、`REFERENCE_SPAN`（被交叉引用的定义或附件条款）。

### 2.6 Suggestion（修改建议）

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `suggestion_id` | string | 是 | 不透明 ID | 建议标识。 |
| `finding_id` | string | 是 | 外键至 `Finding` | 所属命中项。 |
| `suggestion_type` | enum | 是 | `REPLACE_TEXT`、`INSERT_CLAUSE`、`DELETE_TEXT`、`REQUEST_INFO`、`NEGOTIATION_NOTE` | 建议动作类型。 |
| `target_locator_id` | string | 否 | 外键至 `Locator` 或 null | 建议作用的原文位置；`INSERT_CLAUSE` 指插入锚点，`REQUEST_INFO` 可为 null。 |
| `original_text` | string | 否 | 自由文本或 null | 被替换/删除的原文片段（与 locator 的 `quote` 一致）。 |
| `suggested_text` | string | 否 | 自由文本或 null | 建议改写文本；`REPLACE_TEXT` / `INSERT_CLAUSE` 必填。 |
| `rationale` | string | 是 | 自由文本 | 建议理由，说明如何消除该风险。 |
| `template_ref` | object | 否 | `{ "source_key", "version", "citation" }` 或 null | 建议文本所依据的模板/标准条款版本。 |
| `is_auto_applicable` | boolean | 是 | true / false | 是否可在无人工改写的情况下机械应用。`false` 表示只能作为参考文本。 |
| `confidence_score` | number | 是 | [0, 1] | 建议本身的置信度，与 Finding 置信度分开。 |
| `generated_by` | enum | 是 | `SYSTEM_RULE`、`LLM_AGENT`、`HYBRID` | 建议产生主体。 |
| `model_name` | string | 否 | 模型标识串 | LLM 产出时必填。 |
| `prompt_version` | string | 否 | 版本串 | LLM 产出时必填。 |
| `suggestion_status` | enum | 是 | `PROPOSED`、`ACCEPTED`、`ACCEPTED_WITH_EDIT`、`DECLINED`、`STALE` | 建议采纳状态；由人工决定投影，前端不直写。 |
| `created_at` | timestamp | 是 | UTC ISO-8601 | 生成时间。 |

建议是候选文本，不是已生效修改。`ACCEPTED` 仅表示审核者认可该文本，实际文档修改由新文档版本（Teammate 1 的 `document_id` 谱系）体现。

### 2.7 Locator（原文定位）

`locator` 是本主题定义的定位结构体，既作为独立实体持久化（便于多 Finding 复用同一 span），也作为嵌套结构在 API 中返回。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `locator_id` | string | 是 | 不透明 ID | 定位标识。 |
| `document_id` | string | 是 | 外键（Teammate 1） | 所属文档版本。 |
| `parse_result_id` | string | 是 | 外键（Teammate 1 的解析结果） | 定位所基于的解析版本；重新解析后旧定位置为 `LOCATOR_STALE`。 |
| `file_asset_id` | string | 是 | 外键（Teammate 1） | 具体文件（支持正文与附件）。 |
| `locator_status` | enum | 是 | `LOCATOR_VERIFIED`、`LOCATOR_APPROXIMATE`、`LOCATOR_UNAVAILABLE`、`LOCATOR_STALE` | 定位可靠性。仅 `LOCATOR_VERIFIED` 可作为需要精确原文证据的自动判据。 |
| `page_number` | integer | 否 | ≥ 1 或 null | 原文件页码（1 起）。 |
| `paragraph_index` | integer | 否 | ≥ 0 或 null | 解析结构内的段落序号（0 起）。 |
| `section_path` | string[] | 是（可为空） | 章节层级 | 如 `["第5条", "责任限制"]`，用于人可读位置与结构锚定。 |
| `char_start` | integer | 否 | ≥ 0 或 null | 标准化文本中的字符起始偏移（0 起）。 |
| `char_end` | integer | 否 | > `char_start` 或 null | 字符结束偏移，半开区间 `[char_start, char_end)`。 |
| `bbox` | object[] | 是（可为空） | 见下 | 页面坐标框，支持跨页/跨行多框。 |
| `anchor_text` | string | 是 | 自由文本 | 锚点文本：用于人工核验与重锚定的精确摘录。 |
| `anchor_prefix` | string | 是（可为空） | 自由文本 | 锚点前上下文（建议 32–64 字符），用于重锚定消歧。 |
| `anchor_suffix` | string | 是（可为空） | 自由文本 | 锚点后上下文。 |
| `context_excerpt` | string | 是 | 自由文本 | 面向阅读的上下文节选，默认包含命中段前后各 1–2 段。 |
| `content_hash` | string | 是 | `sha256:<hex>` | 校验哈希：对 `anchor_text` 经标准化后计算，用于检测原文或解析变化。 |
| `parse_confidence` | number | 否 | [0, 1] 或 null | 解析/OCR 置信度，来自解析结果；OCR 场景必填。 |
| `created_at` | timestamp | 是 | UTC ISO-8601 | 定位生成时间。 |

`bbox` 每项结构：`{ "page_number": 3, "x": 0.12, "y": 0.44, "width": 0.66, "height": 0.05 }`，坐标为相对页面宽高的 0–1 归一化值，原点在页面左上角。

完整 `locator` 示例：

```json
{
  "locator_id": "loc_7f3a",
  "document_id": "doc_2b91",
  "parse_result_id": "parse_55c0",
  "file_asset_id": "file_main_01",
  "locator_status": "LOCATOR_VERIFIED",
  "page_number": 3,
  "paragraph_index": 42,
  "section_path": ["第5条", "责任限制"],
  "char_start": 10482,
  "char_end": 10525,
  "bbox": [{"page_number": 3, "x": 0.12, "y": 0.44, "width": 0.66, "height": 0.05}],
  "anchor_text": "本协议下任一方的累计责任不超过人民币十万元",
  "anchor_prefix": "除因故意或重大过失外，",
  "anchor_suffix": "。前述限制不适用于保密义务违反。",
  "context_excerpt": "……（命中段前后各一段）……",
  "content_hash": "sha256:9c1e7ab4…",
  "parse_confidence": 0.98,
  "created_at": "2026-08-04T08:31:12Z"
}
```

有效定位至少必须具备 `anchor_text` 与 `content_hash`，且满足以下任一锚点组合：

1. `char_start` + `char_end` + `content_hash`（原生文本，可精确高亮）；
2. `page_number` + 至少一个 `bbox`（扫描件/OCR，可区域高亮）；
3. `section_path` + `paragraph_index` + `anchor_prefix`/`anchor_suffix`（结构化文档，可段落定位）。

三种组合均不满足时，`locator_status` 必须为 `LOCATOR_UNAVAILABLE`，且不得生成伪精确位置。

### 2.8 AuditResult（审核结果汇总）

任务级汇总，一个 `task_id` 对应一条 AuditResult（1:1）。

| 字段名 | 类型 | 必填 | 取值域 / 枚举 | 含义 |
| --- | --- | --- | --- | --- |
| `audit_result_id` | string | 是 | 不透明 ID | 结果标识。 |
| `task_id` | string | 是 | 外键（Teammate 1），唯一 | 所属审核任务。 |
| `document_id` | string | 是 | 外键（Teammate 1） | 被审文档版本。 |
| `ruleset_id` | string | 是 | 外键至 `RuleSet` | 所用规则集版本。 |
| `ruleset_version` | string | 是 | 版本串 | 落库冗余的规则集版本。 |
| `result_status` | enum | 是 | `DRAFT`、`READY_FOR_HUMAN_REVIEW`、`READY_FOR_DELIVERY`、`DELIVERED`、`SUPERSEDED`、`FAILED` | 结果汇总与交付准备状态。**不等同案件批准。** |
| `risk_level` | enum | 是 | `RISK_CRITICAL`、`RISK_HIGH`、`RISK_MEDIUM`、`RISK_LOW`、`RISK_UNDETERMINED` | 任务级风险分级；由最高未处置 Finding 严重度、红线命中和评估完整性共同推导。 |
| `conclusion` | enum | 是 | `CONCLUSION_PENDING`、`CONCLUSION_PASS_WITH_HUMAN_APPROVAL`、`CONCLUSION_NOT_PASS`、`CONCLUSION_INCONCLUSIVE` | 通过/不通过结论。`CONCLUSION_PASS_WITH_HUMAN_APPROVAL` 只能在存在有效人工 `APPROVE` 决定后写入。 |
| `finding_ids` | string[] | 是（可为空） | 外键至 `Finding` | 全部命中项，含已处置项。 |
| `finding_count_total` | integer | 是 | ≥ 0 | 命中总数。 |
| `severity_counts` | object | 是 | 必须包含全部 5 个严重级别键，值可为 0 | 各严重级别命中计数。 |
| `status_counts` | object | 是 | 必须包含全部 `finding_status` 键 | 各处置状态计数。 |
| `evaluation_counts` | object | 是 | `EVALUATED`、`NOT_APPLICABLE`、`INCONCLUSIVE`、`FAILED`、`SKIPPED` 计数 | 规则覆盖情况，用于判断「未发现风险」是否可信。 |
| `rule_coverage_ratio` | number | 是 | [0, 1] | 已成功评估规则数 / 适用规则数。低于治理阈值时禁止自动交付。 |
| `unresolved_required_count` | integer | 是 | ≥ 0 | 仍需人工处置但未处置的命中数；> 0 时不得进入 `READY_FOR_DELIVERY`。 |
| `redline_hit_count` | integer | 是 | ≥ 0 | 红线命中数；> 0 强制人工路径。 |
| `locator_degraded_count` | integer | 是 | ≥ 0 | `LOCATOR_UNAVAILABLE` 或 `LOCATOR_STALE` 的证据涉及的命中数。 |
| `limitations` | string[] | 是（可为空） | 同解释限制词表 | 影响整体结果可用性的限制。 |
| `delivery_summary` | string | 否 | 自由文本或 null | 经授权后可对提交者展示的结论摘要。 |
| `generated_at` | timestamp | 是 | UTC ISO-8601 | 首次生成时间。 |
| `updated_at` | timestamp | 是 | UTC ISO-8601 | 汇总投影更新时间。 |
| `superseded_by_audit_result_id` | string | 否 | 外键或 null | 被后续任务结果替代时的引用。 |

AuditResult 不含 `approved` 布尔字段。案件级批准由 Teammate 3 的 `HumanDecision`（`action = APPROVE`）权威表达；本模型只以 `conclusion` 与 `result_status` 提供投影。

## 3. 实体关系

```text
RuleSet (ruleset_id, ruleset_version)
  │ 1:N（组合关系，规则集发布即冻结成员）
  └─> Rule (rule_id, rule_version)
        │ 1:N（每个任务每条适用规则一次评估）
        └─> RuleEvaluation (evaluation_id) ──── N:1 ──> task_id [T1]
              │ 1:N（0..n，空集不等于无风险）
              └─> Finding (finding_id)  ★主键实体
                    ├─ 1:1 ──> FindingExplanation (explanation_id)
                    ├─ 1:N ──> Suggestion (suggestion_id)
                    ├─ N:M ──> Locator (locator_id)   ← 经 finding_locator 关联
                    └─ N:1 ──> decision_id [T3]（当前生效人工决定，可空）

task_id [T1] ── 1:1 ──> AuditResult (audit_result_id)
                          └─ 1:N（汇总引用）──> Finding

document_id [T1] ── 1:N ──> Locator
parse_result_id [T1] ── 1:N ──> Locator
```

关键基数与生命周期依赖：

| 关系 | 基数 | 说明与外键 |
| --- | --- | --- |
| RuleSet → Rule | 1:N | `Rule.ruleset_id`。规则集版本删除受禁；被历史任务引用的版本必须保留。 |
| Rule → RuleEvaluation | 1:N | `RuleEvaluation.rule_id`。同一任务内同一 `rule_id` 只允许一条评估记录（唯一约束 `(task_id, rule_id)`）。 |
| RuleEvaluation → Finding | 1:N（0..n） | `Finding.evaluation_id`。`finding_ids` 为空必须由 `evaluation_status` 解释原因。 |
| Rule → Finding | 1:N | `Finding.rule_id`。一个 Finding 只归属一条规则版本；跨规则聚合由 `cluster_key` 表达，不合并主键。 |
| Finding → FindingExplanation | 1:1（强制） | `FindingExplanation.finding_id` 唯一。无解释的 Finding 不得对外返回。 |
| Finding → Suggestion | 1:N（0..n） | `Suggestion.finding_id`。可无建议（如 `REQUEST_INFO` 类风险）。 |
| Finding ↔ Locator | N:M | 关联表 `finding_locator(finding_id, locator_id, evidence_role)`。一个 Finding 可有多个定位（跨条款冲突），一个 Locator 可被多个 Finding 引用（风险簇）。 |
| Finding → HumanDecision | N:1（可空） | `Finding.decision_id` 指向当前生效决定；历史决定链由 Teammate 3 模型保存。 |
| task_id → AuditResult | 1:1 | `AuditResult.task_id` 唯一。任务删除/替代时结果转 `SUPERSEDED`，不物理删除。 |
| document_id → Locator | 1:N | `Locator.document_id`。文档版本是 Locator 的生命周期父级：新版本产生新 Locator，旧 Locator 保留为历史。 |

生命周期约束：Finding、Locator、AuditResult 均为任务级不可变事实的载体。文档版本、解析结果或规则集变化时，必须创建新 `task_id` 下的新记录，并通过 `superseded_by_*` 串联，禁止原地覆盖。

## 4. 可解释性与可信度规范

### 4.1 「给人看的解释」与「给系统用的判据」

| 字段 | 分类 | 用途约束 |
| --- | --- | --- |
| `reason_text`、`evidence_summary`、`counter_evidence`、`Suggestion.rationale`、`context_excerpt` | 给人看的解释 | 面向审核者阅读，不参与任何自动路由或阈值判断。禁止包含模型逐步推理、隐藏提示、内部凭据。 |
| `reason_codes`、`extracted_values`、`limitations`、`hit_type` | 双用 | 既展示又可用于统计、筛选与规则校准；必须来自受控词表，不能是自由文本变体。 |
| `confidence_score`、`confidence_band`、`severity`、`is_redline`、`locator_status`、`evaluation_status`、`rule_coverage_ratio` | 给系统用的判据 | 分流、阻断自动放行、结果分级的唯一依据。前端不得重新计算或改写。 |
| `model_name`、`model_version`、`prompt_version`、`rule_version`、`ruleset_version`、`retrieval_refs`、`content_hash` | 溯源判据 | 用于复现与审计；对审核者可见，对提交者默认不可见。 |

### 4.2 LLM 产出必须携带的溯源字段

`Rule.check_type` 为 `CHECK_LLM` 或 `CHECK_HYBRID` 时，对应 Finding 的解释记录必须同时非空：

1. `model_name` 与 `model_version`（哪个模型作出判断）；
2. `prompt_version`（哪个提示模板版本）；
3. `rule_version` 与 `ruleset_version`（哪套规则基线）；
4. 至少一条 `evidence_refs`，且其中至少一项 `role = PRIMARY_SPAN`（证据 span）；
5. `retrieval_refs`（若判断依赖外部依据检索，必须记录查询与来源版本）。

任一项缺失时，后端必须拒绝落库该 Finding，或将其标记为 `EVIDENCE_GAP` 且 `human_review_requirement = REVIEW_REQUIRED`，不得作为自动放行依据。`CHECK_DETERMINISTIC` 规则的 Finding 无需模型字段，但 `rule_version` 与证据 span 仍为必填。

### 4.3 置信度取值范围与分档阈值

`confidence_score` ∈ [0, 1]，保留两位小数。分档由 `RuleSet.confidence_thresholds` 版本化定义，默认值：

| 分档 | 默认区间 | 路由含义 |
| --- | --- | --- |
| `CONFIDENCE_HIGH` | [0.85, 1.00] | 可进入常规复核队列。 |
| `CONFIDENCE_MEDIUM` | [0.60, 0.85) | 必须人工确认，界面提示核对原文。 |
| `CONFIDENCE_LOW` | [0.00, 0.60) | 强制人工复核，禁止自动放行与批量处理。 |
| `CONFIDENCE_UNKNOWN` | 无法计算（模型未返回、评估 `INCONCLUSIVE`） | 与 `CONFIDENCE_LOW` 同等对待，并显式标注「置信度不可用」。 |

严重级别、置信度与处置优先级三者不合并存储。前端排序可组合三者，但不得用其中之一替代另一个；「低置信度的高影响事项」必须仍在列表中可见。

置信度分数不得单独展示为唯一解释。界面呈现必须与可行动说明配对，例如「付款期限提取为 30 天，扫描质量较低，请核对原文」，而非仅显示 `0.62`。

### 4.4 定位失效时的降级展示

触发降级的情形：文档重新解析（`parse_result_id` 变化）、文档新版本、`content_hash` 校验不一致、OCR 修订。

| `locator_status` | 后端行为 | 前端降级展示 |
| --- | --- | --- |
| `LOCATOR_VERIFIED` | 保持可跳转锚点。 | 正常高亮并支持点击定位。 |
| `LOCATOR_APPROXIMATE` | 保留章节/页级锚点，标记需确认。 | 展示「定位需确认」标记，可跳转到段落或页，禁用「精确高亮」承诺。 |
| `LOCATOR_STALE` | 保留原 `anchor_text` 与 `content_hash`，附候选新位置列表（不自动绑定）。 | 展示原摘录 + 候选位置，要求人工重新绑定；不静默跳转到相似文本。 |
| `LOCATOR_UNAVAILABLE` | 不生成坐标或偏移。 | 只展示 `anchor_text` 与解释，明确标注「无法定位到原文，需人工核验」。 |

降级规则：任一 Finding 的全部 Locator 均为 `LOCATOR_UNAVAILABLE` / `LOCATOR_STALE` 时，该 Finding 的 `human_review_requirement` 必须为 `REVIEW_REQUIRED`，且计入 `AuditResult.locator_degraded_count`；该任务不得进入 `READY_FOR_DELIVERY`。定位降级只影响展示与路由，不得据此删除或静默降级 Finding 的 `severity`。

## 5. Finding 状态与人工决策的职责边界

### 5.1 `finding_status` 枚举

| 值 | 含义 | 写入方 |
| --- | --- | --- |
| `OPEN` | 已生成、未处置。 | 系统（Agent 产出时） |
| `PENDING_HUMAN_DECISION` | 已分流进入人工队列，等待决定。 | 系统（分流规则） |
| `CONFIRMED` | 人工确认风险成立。 | 系统投影（依据 `APPROVE` / `EDIT` 决定） |
| `MODIFIED` | 人工改判了严重级别、类别或结论。 | 系统投影（依据 `EDIT` 决定） |
| `FALSE_POSITIVE` | 人工判定为误报。 | 系统投影（依据 `EDIT` + 误报原因） |
| `SUPPLEMENT_REQUIRED` | 需补充材料后才能判断。 | 系统投影（依据 `REQUEST_SUPPLEMENT`） |
| `TRANSFERRED` | 已转交其他责任人/队列。 | 系统投影（依据 `TRANSFER`） |
| `ESCALATED` | 已升级至专家/外部律师。 | 系统投影（依据 `ESCALATE`） |
| `ACCEPTED_WITH_AUTHORIZATION` | 经授权接受风险。 | 系统投影（依据 `ACCEPT_RISK` + `authorization_ref`） |
| `RESOLVED` | 处置完成（含已缓解）。 | 系统投影 |
| `SUPERSEDED` | 因新文档版本/新任务被替代。 | 系统（重审时） |

合法迁移：`OPEN → PENDING_HUMAN_DECISION → {CONFIRMED, MODIFIED, FALSE_POSITIVE, SUPPLEMENT_REQUIRED, TRANSFERRED, ESCALATED, ACCEPTED_WITH_AUTHORIZATION} → RESOLVED`。任何状态均可迁移至 `SUPERSEDED`。`RESOLVED` 与 `SUPERSEDED` 为终态，不可回退；需要改判时由 Teammate 3 的 `CORRECT` / `WITHDRAW` 决定产生新的生效决定并重算投影。

### 5.2 双写冲突的避免规则

1. `finding_status` 是**只读投影**。前端与人工提交接口不得携带该字段作为写入值；人工动作只提交 `decision_id` 相关的决定请求（action、理由、证据、`revision`）。
2. 人工决定的权威记录（操作者、时间、理由、授权、前后值、受理结果）完全归属 Teammate 3 的 `HumanDecision` / `DecisionEffect`；本模型不复制这些字段，只保存 `Finding.decision_id` 作为「当前生效决定」的单向引用。
3. 投影方向单一：`HumanDecision`（accepted）→ `DecisionEffect` → 更新 `Finding.finding_status` / `updated_at` / `revision` / `decision_id`。反向不成立，Finding 状态变化不得回写决定记录。
4. `Suggestion.suggestion_status` 同理，由 `EDIT` / `APPROVE` 决定中的建议采纳信息投影，不接受前端直写。
5. 并发保护：人工提交必须回传 `Finding.revision`；不匹配时后端拒绝为 `rejected_stale`（Teammate 3 的 `decision_status`），并返回当前上下文。前端不得把未确认提交展示为成功。
6. `AuditResult.conclusion` 与 `risk_level` 也是投影，依赖 Finding 状态与人工案件级决定重算；不得由前端或 Agent 直接写入 `CONCLUSION_PASS_WITH_HUMAN_APPROVAL`。

### 5.3 强制人工路径的判据（不可自动放行）

出现以下任一条件，必须将 Finding 置为 `PENDING_HUMAN_DECISION` 且 `human_review_requirement = REVIEW_REQUIRED`，并阻止任务进入 `READY_FOR_DELIVERY`：

- `is_redline = true`；
- `severity ∈ {SEVERITY_CRITICAL, SEVERITY_HIGH}`；
- `confidence_band ∈ {CONFIDENCE_LOW, CONFIDENCE_UNKNOWN}`；
- `locator_ids` 为空，或全部定位为 `LOCATOR_UNAVAILABLE` / `LOCATOR_STALE`；
- `authority_ref_ids` 为空（依据不足）；
- 所属 `RuleEvaluation.evaluation_status ∈ {INCONCLUSIVE, FAILED, SKIPPED}`；
- `hit_type = CONFLICT` 或 `EVIDENCE_GAP`；
- `limitations` 非空。

## 6. 前端必须展示的字段

「不展示会导致用户无法判断」的最小字段集以 ★ 标注。

| 字段 | 展示位置 | 展示理由 |
| --- | --- | --- |
| ★ `Finding.severity` | 结果列表 + 严重级别徽标 | 决定处理顺序。徽标必须文字 + 图标 + 形状组合，不以颜色为唯一编码（WCAG 2.2 1.4.1）。 |
| ★ `Finding.title` | 结果列表行 | 一眼判断问题性质。 |
| ★ `Finding.summary` | 结果列表行 / 命中详情侧栏 | 无摘要则需逐条打开详情，队列不可用。 |
| ★ `Finding.category` | 结果列表（分组/筛选） | 按条款类型组织复核工作。 |
| ★ `Finding.finding_status` | 结果列表状态列 | 区分「风险判断」与「处理结论」两个维度。 |
| ★ `Finding.confidence_band` | 结果列表 + 详情侧栏 | 判断是否需要重点核对；分数单独出现无意义，必须与说明配对。 |
| `Finding.confidence_score` | 命中详情侧栏（审核者角色） | 支持高级审核者精细判断与阈值校准反馈。 |
| ★ `Finding.is_redline` | 结果列表徽标 | 红线项禁止批量关闭，需显式标识。 |
| ★ `Locator.page_number` + `section_path` | 结果列表位置列（如「第 3 页 · 5. 责任限制」） | 无位置信息无法回到原文核验。 |
| ★ `Locator.anchor_text` | 结果列表短摘录 + 原文高亮 | 摘录是列表可判性的核心；也是定位失效时唯一可核验线索。 |
| ★ `Locator.context_excerpt` | 命中详情侧栏 / 原文阅读器 | 仅高亮关键词会丢失法律限定条件，上下文是判断的一部分。 |
| ★ `Locator.locator_status` | 原文高亮旁的状态标记 | 必须让用户知道定位是否可信，避免误信错误跳转。 |
| `Locator.bbox` / `char_start` / `char_end` | 原文阅读器（内部使用，不显示数值） | 驱动高亮渲染；数值本身不面向用户。 |
| `Locator.parse_confidence` | 原文高亮旁提示（OCR 场景） | 低质量 OCR 上不承诺精确定位。 |
| ★ `FindingExplanation.reason_text` | 命中详情侧栏 | 回答「为什么被判定为风险」，否则用户无法评估结论。 |
| ★ `FindingExplanation.evidence_summary` + `evidence_refs` | 证据引用块 | 将结论绑定到具体原文 span，支持独立复核。 |
| ★ `FindingExplanation.limitations` | 命中详情侧栏（非空时置顶） | 可行动的不确定性提示，防止虚假确定感。 |
| ★ `FindingExplanation.authority_ref_ids` → `citation` | 证据引用块 | 展示判断依据及其版本；为空必须显示「依据不足」。 |
| `FindingExplanation.extracted_values` | 命中详情侧栏（证据层，按需展开） | 便于核对金额、期限等结构化值。 |
| `FindingExplanation.counter_evidence` | 命中详情侧栏 | 提示可能推翻结论的上下文，降低误报成本。 |
| `FindingExplanation.model_name` / `model_version` / `prompt_version` | 命中详情侧栏「溯源」区（审核者角色） | 支持可复现审计；对提交者默认隐藏。 |
| ★ `FindingExplanation.generated_by` | 命中详情侧栏标记 | 必须区分规则命中与模型推断，模型推断无原文依据时标注「待人工确认」。 |
| ★ `Rule.title` + `rule_version` + `ruleset_version` | 命中详情侧栏「适用规则」区 | 说明用了哪套标准判断，是复核与申诉的前提。 |
| ★ `Suggestion.suggested_text` + `rationale` | 命中详情侧栏建议区 | 给出可执行的下一步；无建议时也需明确说明「需人工拟定」。 |
| `Suggestion.is_auto_applicable` / `suggestion_status` | 建议区 | 区分参考文本与可直接应用文本，避免误用。 |
| ★ `AuditResult.risk_level` + `conclusion` | 结果页头部 | 任务级结论与风险分级是页面主信息。 |
| ★ `AuditResult.severity_counts` + `finding_count_total` | 结果页头部统计 | 快速判断工作量与风险分布。 |
| ★ `AuditResult.rule_coverage_ratio` + `evaluation_counts` | 结果页头部提示 | 覆盖不全时「未发现风险」不可信，必须显式提示。 |
| ★ `AuditResult.limitations` | 结果页头部横幅（非空时） | 整体限制影响结果可用性判断。 |
| ★ `AuditResult.unresolved_required_count` | 结果页头部 | 明确还有多少必处置项，防止误以为审核已完成。 |

未获授权字段（内部规则配置、提示词正文、检索原始结果、其他案件信息）不得返回或以隐藏控件替代权限控制。

<!--CONT-->







