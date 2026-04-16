# DB Script Skills

一套面向 PostgreSQL 的数据库脚本编写与设计文档生成工具集，适用于遵循《数据库脚本规范 V1.2》的项目。全程支持单系统与多系统两种目录布局。

## 架构分层

本项目按 **Skill（能力）+ Workflow（流程）** 两层组织：

- **Skill**：提供原子化的脚本工具，每个 Skill 专注做一类事情（生成脚本、生成文档、本地无库修改）。
- **Workflow**：按实际业务场景编排多个 Skill/脚本，定义完整的执行步骤和决策分支。

## 目录结构

```
db-script-skills/
├── README.md
├── db-script-generator/          # Skill：数据库脚本生成
│   ├── SKILL.md
│   ├── references/               # 规范与规则引用
│   │   └── db-rules.md
│   └── scripts/
│       ├── init_project_dirs.py
│       ├── generate_db_scripts.py
│       ├── apply_schema_changes.py
│       ├── sync_db_from_changes.py
│       ├── align_sql_values.py
│       ├── check_db_consistency.py
│       ├── fix_cx_fld.py
│       ├── generate_views.py
│       ├── generate_procs.py
│       ├── generate_triggers.py
│       └── run_all.py
├── db-design-doc-generator/      # Skill：数据库设计文档生成与双向转换
│   ├── SKILL.md
│   └── scripts/
│       ├── generate_excel.py
│       ├── generate_er.py
│       ├── generate_excel_from_sql.py
│       ├── generate_er_from_sql.py
│       └── generate_sql_from_excel.py
├── db-workflow-orchestrator/     # Skill：工作流编排器
│   ├── SKILL.md
│   └── references/
│       ├── init-project.md
│       ├── schema-change.md
│       ├── generate-design-docs.md
│       ├── generate-scripts-from-excel.md
│       └── align-sql-files.md
├── local-script-extensions/      # Skill：本地无库脚本同步
│   ├── SKILL.md
│   ├── changes_example.json
│   └── update_db_scripts.py
└── workflows/                    # Workflow：业务场景流程（源码参考）
    ├── init-project.md
    ├── schema-change.md
    ├── generate-design-docs.md
    ├── generate-scripts-from-excel.md
    └── align-sql-files.md
```

---

## 快速开始（按 Workflow）

### 场景1：从已有数据库初始化项目

参见 [`workflows/init-project.md`](workflows/init-project.md)。

核心调用：
```bash
# 1. 初始化目录
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "./my-project" --layout single

# 2. 生成全量脚本
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/01-Application" \
  --schema zgis --sys 0 --major 90

# 3. 生成视图、函数/存储过程、触发器（可选）
python db-script-generator/scripts/generate_views.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/01-Application" \
  --schema zgis

python db-script-generator/scripts/generate_procs.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/02-Procs" \
  --schema zgis

python db-script-generator/scripts/generate_triggers.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/02-Procs" \
  --schema zgis
```

### 场景2：表结构变更与新建表

参见 [`workflows/schema-change.md`](workflows/schema-change.md)。

核心调用链：
1. `sync_db_from_changes.py`（dry-run → apply）
2. `apply_schema_changes.py`（生成增量脚本）
3. `generate_db_scripts.py`（重新生成全量脚本）
4. `align_sql_values.py`（格式化对齐）

> 如果不想连接数据库，直接使用 `local-script-extensions/update_db_scripts.py`。

### 场景3：生成设计文档

参见 [`workflows/generate-design-docs.md`](workflows/generate-design-docs.md)。

支持两种数据来源：**数据库** 或 **全量 SQL 脚本目录**。

```bash
# 从数据库生成
python db-design-doc-generator/scripts/generate_excel.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/00-Design/01-Excel" \
  --schema zgis

# 从全量 SQL 脚本生成
python db-design-doc-generator/scripts/generate_excel_from_sql.py \
  --input-dir "./my-project/01-Application" \
  --output-dir "./my-project/00-Design/01-Excel"
```

### 场景4：从 Excel 设计文档生成全量 SQL 脚本

参见 [`workflows/generate-scripts-from-excel.md`](workflows/generate-scripts-from-excel.md)。

```bash
python db-design-doc-generator/scripts/generate_sql_from_excel.py \
  --input "./design.xlsx" \
  --output-dir "./my-project/01-Application" \
  --sys "0"
```

### 场景5：批量格式化对齐已有 SQL 脚本

参见 [`workflows/align-sql-files.md`](workflows/align-sql-files.md)。

```bash
# 单个文件
python db-script-generator/scripts/align_sql_values.py \
  --input "./my-project/01-Application/02-cx_fld.sql"

# 批量整个目录（PowerShell）
Get-ChildItem "./my-project/01-Application/*.sql" | ForEach-Object {
    python db-script-generator/scripts/align_sql_values.py --input $_.FullName
}
```

---

## Skill 速查

### db-script-generator

| 脚本 | 用途 |
|------|------|
| `generate_db_scripts.py` | 从数据库生成全量 SQL 脚本 |
| `apply_schema_changes.py` | 根据 JSON 变更生成增量升级脚本 |
| `sync_db_from_changes.py` | 将变更同步到数据库（dry-run/apply） |
| `align_sql_values.py` | 对 SQL INSERT 做中文宽度对齐 |
| `check_db_consistency.py` | 数据库配置一致性检查 |
| `fix_cx_fld.py` | 自动修复常见配置问题 |
| `generate_views.py` | 从数据库生成视图脚本 |
| `generate_procs.py` | 从数据库生成函数/存储过程脚本 |
| `generate_triggers.py` | 从数据库生成触发器脚本 |
| `init_project_dirs.py` | 初始化标准项目目录 |
| `run_all.py` | 一键串行生成多个子系统全量脚本 |

### db-design-doc-generator

| 脚本 | 用途 | 方向 |
|------|------|------|
| `generate_excel.py` | 从 PostgreSQL 生成 Excel 表结构文档 | DB → Excel |
| `generate_er.py` | 从 PostgreSQL 生成 SVG ER 图 | DB → ER |
| `generate_excel_from_sql.py` | 从全量 SQL 脚本生成 Excel | SQL → Excel |
| `generate_er_from_sql.py` | 从全量 SQL 脚本生成 SVG ER 图 | SQL → ER |
| `generate_sql_from_excel.py` | 从 Excel 反向生成全量 SQL 脚本 | Excel → SQL |

### db-workflow-orchestrator

| 参考文档 | 覆盖场景 |
|---------|---------|
| `init-project.md` | 从已有数据库初始化项目 |
| `schema-change.md` | 表结构变更与新建表 |
| `generate-design-docs.md` | 生成设计文档（Excel + ER） |
| `generate-scripts-from-excel.md` | 从 Excel 反向生成 SQL |
| `align-sql-files.md` | 批量格式化对齐 SQL |

> 本 Skill 用于编排上述多个 Skill 的完整业务流程。

### local-script-extensions

| 脚本 | 用途 |
|------|------|
| `update_db_scripts.py` | 不连数据库，直接根据 JSON 修改本地全量/增量脚本 |

---

## 环境要求

- Python 3.10+
- `psycopg2` 或 `psycopg2-binary`
- `openpyxl`、`svglib` 等（设计文档生成器使用，详见各 SKILL.md）
- `@mermaid-js/mermaid-cli`（ER 图生成使用，可选）

## License

MIT
