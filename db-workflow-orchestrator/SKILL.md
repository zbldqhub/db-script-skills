---
name: db-workflow-orchestrator
description: Orchestrate end-to-end database development workflows for PostgreSQL projects following the Database Script Specification V1.2. Use when the user asks for multi-step procedures such as initializing a project from an existing database, performing schema changes (creating tables or adding columns), generating design deliverables (Excel specs and ER diagrams), generating full SQL scripts from Excel design documents, or batch-aligning existing SQL scripts. This skill coordinates db-script-generator, db-design-doc-generator, and local-script-extensions into complete business workflows.
---

# 数据库工作流编排器

本 Skill 不提供原子脚本，而是提供端到端的业务流程指南，用于编排 `db-script-generator`、`db-design-doc-generator` 和 `local-script-extensions` 多个 Skill，完成复杂的多步骤任务。

## 适用场景

| 场景 | 触发关键词 | 参考文档 |
|------|-----------|---------|
| 从已有数据库初始化项目 | "初始化项目"、"从数据库生成脚本"、"生成标准目录" | [references/init-project.md](references/init-project.md) |
| 表结构变更与新建表 | "新建表"、"加字段"、"改表结构"、"生成增量脚本" | [references/schema-change.md](references/schema-change.md) |
| 生成设计文档 | "生成设计文档"、"出 Excel"、"画 ER 图"、"表结构文档" | [references/generate-design-docs.md](references/generate-design-docs.md) |
| 从 Excel 设计文档生成 SQL | "从 Excel 生成脚本"、"Excel 转 SQL"、"按设计文档建表" | [references/generate-scripts-from-excel.md](references/generate-scripts-from-excel.md) |
| 批量格式化对齐 SQL | "格式化 SQL"、"对齐脚本"、"整理 INSERT"、"批量对齐" | [references/align-sql-files.md](references/align-sql-files.md) |

## 核心原则

1. **先判断场景**：根据用户的表述，匹配上表中的某一个 Workflow。
2. **收集必要信息**：每个 Workflow 都有"需要收集的信息"小节，按清单询问或推断。
3. **按步骤执行**：Workflow 中已经给出了具体的脚本调用顺序和参数示例，直接调用对应 Skill 下的脚本即可。
4. **遵循规范**：所有操作必须遵循《数据库脚本规范 V1.2》。核心规则参见 `db-script-generator/references/db-rules.md`。

## 常见决策分支

### 用户说"表结构变更"时的分支

- **有数据库连接** → 走 `schema-change.md` 的标准 5 步流程（JSON → sync DB → 增量 → 重生成全量 → 对齐）
- **不想连数据库** → 直接使用 `local-script-extensions/update_db_scripts.py` 本地修改

### 用户说"生成设计文档"时的分支

- **有数据库连接** → 调用 `db-design-doc-generator/scripts/generate_excel.py` + `generate_er.py`
- **只有全量 SQL 脚本** → 调用 `generate_excel_from_sql.py` + `generate_er_from_sql.py`

### 用户说"初始化项目"时的分支

直接调用 `init_project_dirs.py --project-root <path>` 生成标准目录，随后按需生成全量脚本、视图、函数/存储过程、触发器。

## 外部依赖

本 Skill 依赖以下 Skill 提供的底层脚本能力：

- `db-script-generator`：目录初始化、全量脚本生成、增量脚本生成、数据库同步、格式化对齐、一致性检查与修复
- `db-design-doc-generator`：Excel / ER 图生成、SQL 反向生成
- `local-script-extensions`：无数据库连接的本地脚本修改
