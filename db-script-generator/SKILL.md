---
name: db-script-generator
description: 根据《数据库脚本规范V1.2》从 PostgreSQL 元数据生成标准化的全量 SQL 脚本（01-table ~ 11-cx_plugin）、增量更新脚本（YYYYMMDD.sql）、数据库一致性检查报告以及自动修复脚本。支持单系统与多系统两种项目布局。Use when the user asks to generate SQL installation scripts, delta upgrade scripts, database consistency checks, auto-fixes for cx_fld / cx_entity metadata, or schema changes (create/alter tables).
---

# 数据库脚本生成器 (DB Script Generator V1.2)

本 Skill 严格遵循《数据库脚本规范 V1.2》执行所有操作，按使用场景分为两类：

1. **场景1：从已有数据库初始化项目** —— 已有 DB，生成标准目录和全量脚本。
2. **场景2：表结构变更与新建表** —— 用户提供需求，生成增量脚本并同步更新全量脚本。

---

## 场景1：从已有数据库初始化项目

### 你需要询问用户的问题

1. **项目根目录**（`project-root`）放在哪里？
2. **单系统还是多系统？**
   - **单系统**：`01-Application/` 下直接生成脚本文件。
   - **多系统**：`01-Application/<子系统名>/` 下分别生成脚本文件。如果是多系统，需要列出各子系统的**名称**和对应的 **sys 码**。
3. 数据库连接 URL、schema 名（默认 `zgis`）。
4. 需要按哪些 `major` 生成脚本？（如果用户不清楚，可传空，默认生成 `cx_entity.major > 0` 的所有表）
5. 是否需要同时生成 `09-data.sql`、`10-cx_func.sql`、`11-cx_plugin.sql`？
   > **默认不生成**。只有用户明确说“要系统配置脚本”时才加 `--with-config`。

### 目录结构示例

#### 单系统
```
<project-root>/
├── 00-Design/
├── 01-Application/
│   ├── 01-table.sql
│   ├── 02-cx_fld.sql
│   ├── 03-cx_fldvalue.sql
│   ├── 04-cx_entity.sql
│   ├── 05-index.sql
│   ├── 09-data.sql          (仅 --with-config)
│   ├── 10-cx_func.sql       (仅 --with-config)
│   └── 11-cx_plugin.sql     (仅 --with-config)
├── 02-Procs/
├── 03-Upgrade/
├── 04-Release/
├── 05-TestData/
└── 06-Temp/
```

#### 多系统
```
<project-root>/
├── 00-Design/
├── 01-Application/
│   ├── 15-表务&抄表管理系统/
│   │   ├── 01-table.sql
│   │   ├── 02-cx_fld.sql
│   │   ├── 03-cx_fldvalue.sql
│   │   ├── 04-cx_entity.sql
│   │   └── 05-index.sql
│   ├── 18-收费管理系统/
│   │   ├── 01-table.sql
│   │   ├── 02-cx_fld.sql
│   │   ├── 03-cx_fldvalue.sql
│   │   ├── 04-cx_entity.sql
│   │   └── 05-index.sql
├── 02-Procs/
├── 03-Upgrade/
├── 04-Release/
├── 05-TestData/
└── 06-Temp/
```

### 执行步骤

#### 步骤1：初始化目录
```bash
# 单系统
python scripts/init_project_dirs.py --project-root "<project-root>" --layout single

# 多系统
python scripts/init_project_dirs.py \
  --project-root "<project-root>" \
  --layout multi \
  --systems '["15-表务&抄表管理系统","18-收费管理系统"]'
```

#### 步骤2：生成全量脚本
- **单系统**：直接调用 `generate_db_scripts.py`
- **多系统**：为每个子系统分别调用，指定各自的 `--sys`、`--major` 和 `--output-dir`

```bash
# 单系统示例
python scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --sys 0 \
  --major 90

# 多系统示例（15-表务，sys=15，major=41）
python scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application/15-表务&抄表管理系统" \
  --schema zgis \
  --sys 15 \
  --major 41
```

如需同时生成 `09/10/11` 系统配置脚本，追加 `--with-config`：
```bash
python scripts/generate_db_scripts.py \
  --db-url "postgresql://..." \
  --output-dir "<project-root>/01-Application" \
  --major 90 \
  --with-config
```

#### 步骤3：一键总控（可选）
配置文件 `config.json` 示例（多系统）：
```json
{
  "db_url": "postgresql://user:pass@host:port/dbname",
  "schema": "zgis",
  "project_root": "/path/to/project",
  "layout": "multi",
  "systems": [
    {"name": "15-表务&抄表管理系统", "sys": "15", "majors": [41, 42]},
    {"name": "18-收费管理系统", "sys": "18", "majors": [47]}
  ]
}
```

单系统兼容旧格式（`majors` 列表）：
```json
{
  "db_url": "postgresql://user:pass@host:port/dbname",
  "schema": "zgis",
  "sys": "0",
  "project_root": "/path/to/project",
  "majors": [90]
}
```

执行：
```bash
python scripts/run_all.py --config config.json
```

---

## 场景2：表结构变更与新建表

> **与场景3的本质区别**：场景2是“生成新脚本”，必须知道增量和全量脚本的输出位置；场景3是“格式化已有脚本”，直接在原文件上修改。

### 你需要询问用户的问题

1. **项目根目录**（`project-root`）在哪里？
2. **单系统还是多系统？**
   - 多系统时：该表属于哪个**子系统**？这关系到：
     - `cx_fld.sys` 的取值
     - 增量脚本和全量脚本的输出位置（`01-Application/<子系统名>/`）
3. **表的主类型（`major`）和子类型范围（`minor`）？**
4. **表名前缀要求？**（例如 `edu_student`、`hr_employee`）
5. **字段清单**：字段名、数据类型、中文名、是否可空、显示类型（`disptype`）、显示顺序（`disporder`）等。
6. **是否有字典值（`cx_fldvalue`）？**

### 执行步骤

#### 步骤1：构建变更描述文件
根据用户需求，生成两个 JSON 文件：

- `changes.json`：DDL 变更（`create_table`、`add_column`、`drop_column`、`alter_type`）+ 配置变更（`add_fld`、`add_fldvalue`）。
- `table_meta.json`：元数据插入/更新（`cx_entity`、`cx_fld`、`cx_fldvalue`）。

**`changes.json` 示例（新建表 + 加字段 + 配置）：**
```json
[
  {
    "action": "create_table",
    "table": "student",
    "columns": [
      {"name": "id", "type": "serial", "nullable": false, "comment": "ID"},
      {"name": "code", "type": "varchar(32)", "nullable": true, "comment": "编码"},
      {"name": "name", "type": "varchar(64)", "nullable": true, "comment": "名称"},
      {"name": "age", "type": "integer", "nullable": true, "comment": "年龄"}
    ],
    "pk": ["id"]
  },
  {
    "action": "add_column",
    "table": "teacher",
    "column": "email",
    "type": "varchar(128)",
    "nullable": true
  },
  {
    "action": "add_fld",
    "table": "student",
    "sys": "100",
    "fld": {"colname": "code", "namec": "编码", "disptype": "1", "isnum": "0", "disporder": "1", "newedit": "1", "editable": "1", "nullable": "1"}
  },
  {
    "action": "add_fldvalue",
    "table": "student",
    "column": "status",
    "sys": "100",
    "values": [{"dbvalue": "0", "dispc": "正常", "disporder": "1"}]
  }
]
```

**`table_meta.json` 示例：**
```json
{
  "entities": [
    {
      "name": "student",
      "namec": "学生表",
      "type": "1",
      "major": "90",
      "minor": "1",
      "domains": "1",
      "glmaj": "0",
      "glmin": "0",
      "log": "0"
    }
  ],
  "flds": {
    "student": [
      {"sys": "100", "colname": "code", "namec": "编码", "disptype": "1", "isnum": "0", "disporder": "1", "newedit": "1", "editable": "1", "nullable": "1"}
    ]
  },
  "fldvalues": {
    "student": {
      "status": [
        {"sys": "100", "dbvalue": "0", "dispc": "正常", "disporder": "1"}
      ]
    }
  }
}
```

#### 步骤2：将变更同步到数据库（默认 dry-run）
> **说明**：全量脚本 `generate_db_scripts.py` 是从数据库元数据生成的。为了让全量脚本能反映最新结构，**必须先把变更写入数据库**，再重新生成全量脚本。

```bash
# 先预览
python scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json

# 确认无误后执行
python scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json \
  --apply
```

#### 步骤3：生成增量脚本
```bash
python scripts/apply_schema_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --project-root "<project-root>" \
  --author "你的名字" \
  --changes changes.json
```

增量脚本将输出到 `<project-root>/03-Upgrade/YYYYMMDD.sql`。

#### 步骤4：重新生成该子系统的全量脚本
```bash
# 单系统
python scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --sys <sys> \
  --major <major>

# 多系统
python scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application/<子系统名>" \
  --schema zgis \
  --sys <sys> \
  --major <major>
```

> 重新生成时，该 `major` 下的所有表都会被整体重写，确保 `01-Application` 下的全量脚本与数据库完全一致。

---

## 核心规则

### 规则1：`cx_fld` 永远不要配置 `id` 字段

- `id` 由数据库自增主键管理，不允许出现在 `cx_fld` 配置中。
- 所有生成脚本、修复脚本、增量变更脚本、数据库同步脚本必须强制排除 `id`。
- 该规则来源于全局 `~/.agents/AGENTS.md`，所有项目通用。

### 规则2：所有表必须有主键，主键名称为 `id`，默认自增

- **每个表必须包含 `id` 字段作为主键**。
- **非特殊指定时，`id` 设置为自增**：`id serial primary key`。
- **建表语句中**，`id` 的主键约束直接写在字段定义后面：`id serial primary key`。
- **禁止**在 `CREATE TABLE` 的字段列表末尾再写一行 `CONSTRAINT xxx PRIMARY KEY (id)`。

---

## 数据库配置一致性检查

```bash
python scripts/check_db_consistency.py \
  --db-url "postgresql://..." \
  --schema zgis \
  --output report.sql
```

检查项：
- `cx_fld` 中配置了被禁止的 `id` 字段
- 实际表存在但 `cx_fld` 中缺失的字段（排除 `id`）
- `cx_fld` 中存在但实际表不存在的 orphan 字段
- 非 `act%` 表中 `colname` 未小写的记录
- `cx_entity` 中表名在实际 schema 中不存在

---

## 数据库配置自动修复

```bash
# 预览修复 SQL（默认 dry-run）
python scripts/fix_cx_fld.py \
  --db-url "postgresql://..." \
  --schema zgis \
  --output fix.sql

# 真正执行修复
python scripts/fix_cx_fld.py \
  --db-url "postgresql://..." \
  --schema zgis \
  --apply
```

自动修复内容：
- 将非 `act%` 表的 `colname` 统一改为小写
- **删除 `cx_fld` 中所有 `id` 的违规配置**
- 删除 orphan `cx_fld` 记录
- 同步 `cx_fld.sys` 与 `cx_entity.sys`

---

## 场景3：格式化对齐已有 SQL 脚本

> **与场景2的本质区别**：场景3是“修改已有脚本”，直接在原文件上对齐；**不需要问增量/全量脚本路径**，只需要知道文件或目录位置即可。

如果用户给了一个或一批已写好的 SQL 脚本，要求对 `INSERT INTO ... VALUES (...)` 语句做中文显示宽度对齐，可以直接调用对齐脚本。

### 单个文件（直接覆盖原文件）
```bash
python scripts/align_sql_values.py --input "D:\project\01-Application\02-cx_fld.sql"
```

### 批量对齐整个目录（PowerShell）
```powershell
Get-ChildItem "D:\project\01-Application\*.sql" | ForEach-Object {
    python scripts/align_sql_values.py --input $_.FullName
}
```

### 批量对齐整个目录（CMD）
```cmd
for %f in ("D:\project\01-Application\*.sql") do python scripts/align_sql_values.py --input "%f"
```

> **说明**：
> - 该脚本为**原地修改**（in-place），会直接覆盖传入的文件内容。
> - **默认处理所有 `cx_` 前缀的配置表**（如 `cx_fld`、`cx_fldvalue`、`cx_entity`、`cx_func`、`cx_funcgrp`、`cx_plugin` 等）。
> - 如需额外指定其他表，可使用 `--tables` 参数：`--tables "teacher,student"`。
> - **排除项**：测试数据表、日志表、大量业务数据表的 INSERT 不建议用此脚本对齐。

---

## 命名规范速查

| 对象类型 | 命名格式 | 示例 |
|---------|---------|------|
| 表 | 小写+下划线，模块前缀 | `mr_book` |
| 字段 | 小写+下划线 | `book_id`, `create_time` |
| 视图 | `v_表名_描述` | `v_mr_book_summary` |
| 函数 | `f_描述` | `f_calc_water_fee()` |
| 存储过程 | `p_描述` | `p_sync_user_data()` |
| 触发器 | `表名_时机_操作` | `mr_book_BI` |
| 索引 | `表名_字段名` | `mr_book_book_no` |
| 序列 | `表名_字段名_seq` | `mr_book_id_seq` |
| 临时对象 | `tmp_` 前缀 | `tmp_import_data` |

---

## 脚本清单

所有脚本位于 `scripts/` 目录：

| 脚本 | 用途 |
|------|------|
| `generate_db_scripts.py` | 全量生成 01-table ~ 11-cx_plugin，自动对齐 |
| `align_sql_values.py` | 对 SQL 文件中的 INSERT 执行中文显示宽度对齐 |
| `apply_schema_changes.py` | 读取 JSON 变更清单，生成 `03-Upgrade/YYYYMMDD.sql` |
| `sync_db_from_changes.py` | 将 DDL 和元数据变更实际执行到数据库（默认 dry-run） |
| `check_db_consistency.py` | 输出数据库配置一致性检查报告 |
| `fix_cx_fld.py` | 自动修复常见配置问题（默认 dry-run） |
| `init_project_dirs.py` | 一键初始化标准目录（支持 `--layout single|multi`） |
| `run_all.py` | 一键串行生成所有交付物（支持多系统 `systems` 数组） |
