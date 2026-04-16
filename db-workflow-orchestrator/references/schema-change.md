# Workflow：表结构变更与新建表

## 触发条件

用户说"新建表"、"加字段"、"改表结构"、"生成增量脚本"、"表结构变更"等。

## 需要收集的信息

1. **项目根目录**（`project-root`）在哪里？
2. **单系统还是多系统？**
   - 多系统时：该表属于哪个**子系统**？这关系到 `cx_fld.sys` 的取值，以及增量脚本和全量脚本的输出位置（`01-Application/<子系统名>/`）
3. **表的主类型（`major`）和子类型范围（`minor`）**
4. **表名前缀要求**（例如 `edu_student`、`hr_employee`）
5. **字段清单**：字段名、数据类型、中文名、是否可空、显示类型（`disptype`）、显示顺序（`disporder`）等
6. **是否有字典值（`cx_fldvalue`）**
7. **数据库连接 URL** 和 **schema 名**（默认 `zgis`）
8. **增量脚本作者名**

## 执行步骤

### 步骤1：构建变更描述文件

根据用户需求，生成两个 JSON 文件：

- `changes.json`：DDL 变更（`create_table`、`add_column`、`drop_column`、`alter_type`）+ 配置变更（`add_fld`、`add_fldvalue`）
- `table_meta.json`：元数据插入/更新（`cx_entity`、`cx_fld`、`cx_fldvalue`）

> **规则校验**：遵循 [`db-script-generator/references/db-rules.md`](../db-script-generator/references/db-rules.md) 中的核心规则，包括：`cx_fld` 中永远不要配置 `id` 字段；所有表必须包含 `id serial primary key`。

### 步骤2：将变更同步到数据库（dry-run → apply）

```bash
# 先预览
python db-script-generator/scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json

# 确认无误后执行
python db-script-generator/scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json \
  --apply
```

### 步骤3：生成增量脚本

```bash
python db-script-generator/scripts/apply_schema_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --project-root "<project-root>" \
  --author "作者名" \
  --changes changes.json
```

增量脚本输出到 `<project-root>/03-Upgrade/YYYYMMDD.sql`。

### 步骤4：重新生成该子系统的全量脚本

```bash
# 单系统
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --sys <sys> \
  --major <major>

# 多系统
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application/<子系统名>" \
  --schema zgis \
  --sys <sys> \
  --major <major>
```

> 重新生成时，该 `major` 下的所有表都会被整体重写，确保 `01-Application` 下的全量脚本与数据库完全一致。

### 步骤5：格式化对齐

对更新后的全量脚本调用 `align_sql_values.py`：

```bash
python db-script-generator/scripts/align_sql_values.py \
  --input "<project-root>/01-Application/02-cx_fld.sql"
```

## 替代路径：无数据库本地修改

如果用户**不想连接数据库**，直接使用 `local-script-extensions`：

```bash
python local-script-extensions/update_db_scripts.py --config changes.json
```

此时无需执行步骤2和步骤4，只需准备好符合 `local-script-extensions` 格式的 JSON 配置文件即可。
