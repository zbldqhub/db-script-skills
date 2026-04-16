# Workflow：表结构变更与新建表

## 触发条件

用户说"新建表"、"加字段"、"改表结构"、"生成增量脚本"、"表结构变更"等。

## 优先原则

**默认优先使用本地无库方式修改脚本**。除非用户明确要求"同步到数据库"、"连库执行"、"先改数据库"，否则不连接数据库。

## 需要收集的信息

1. **项目根目录**（`project-root`）在哪里？
2. **单系统还是多系统？**
   - 多系统时：该表属于哪个**子系统**？这关系到 `cx_fld.sys` 的取值，以及增量脚本和全量脚本的输出位置（`01-Application/<子系统名>/`）
3. **表的主类型（`major`）和子类型范围（`minor`）**
4. **表名前缀要求**（例如 `edu_student`、`hr_employee`）
5. **字段清单**：字段名、数据类型、中文名、是否可空、显示类型（`disptype`）、显示顺序（`disporder`）等
6. **是否有字典值（`cx_fldvalue`）**
7. **增量脚本作者名**
8. 是否要求**同步到数据库**？（默认否）

---

## 默认路径：本地无库修改（推荐）

### 步骤1：构建变更描述文件

根据用户需求，生成 `changes.json`：

```json
{
  "project_root": "<project-root>",
  "system": "15-表务&抄表管理系统",
  "target_upgrade": "03-Upgrade/20260416.sql",
  "author": "作者名",
  "comment": "新增 student 表及相关配置",
  "changes": [
    {
      "action": "create_table",
      "table": "student",
      "namec": "学生表",
      "major": "90",
      "minor": "1",
      "columns": [
        {"name": "id", "definition": "serial primary key", "comment": "ID"},
        {"name": "code", "definition": "varchar(32)", "comment": "编码"},
        {"name": "name", "definition": "varchar(64)", "comment": "姓名"}
      ]
    },
    {
      "action": "add_columns",
      "table": "teacher",
      "columns": [
        {"name": "email", "definition": "varchar(128)", "comment": "邮箱"}
      ]
    },
    {
      "action": "add_fld",
      "table": "student",
      "sys": "15",
      "flds": [
        {"colname": "code", "namec": "编码", "disptype": 1, "isnum": 0, "disporder": 1, "newedit": 1, "editable": 1, "nullable": 1}
      ]
    },
    {
      "action": "add_fldvalue",
      "table": "student",
      "sys": "15",
      "values": [
        {
          "colname": "status",
          "items": [
            {"disporder": 1, "dbvalue": "0", "dispc": "正常"}
          ]
        }
      ]
    }
  ]
}
```

> **规则校验**：遵循 `db-script-generator/references/db-rules.md` 中的核心规则，包括：`cx_fld` 中永远不要配置 `id` 字段；所有表必须包含 `id serial primary key`。

### 步骤2：执行本地脚本同步

```bash
python local-script-extensions/update_db_scripts.py --config changes.json
```

该脚本会自动：
- 修改 `01-table.sql`（`create_table`、`add_columns`、`drop_columns`）
- 修改 `02-cx_fld.sql`（`add_fld`、`remove_fld`）
- 修改 `03-cx_fldvalue.sql`（`add_fldvalue`、`remove_fldvalue`）
- 修改 `04-cx_entity.sql`（`create_table` 时追加实体记录）
- 生成增量脚本到 `03-Upgrade/YYYYMMDD.sql`

### 步骤3：格式化对齐

```bash
python db-script-generator/scripts/align_sql_values.py \
  --input "<project-root>/01-Application/02-cx_fld.sql"

python db-script-generator/scripts/align_sql_values.py \
  --input "<project-root>/01-Application/03-cx_fldvalue.sql"
```

---

## 替代路径：同步到数据库（用户明确要求时）

如果用户明确要求"先改数据库"，则走以下流程：

### 步骤1：构建变更描述文件

生成 `changes.json` + `table_meta.json`（元数据插入/更新）。

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

### 步骤4：重新生成该子系统的全量脚本

```bash
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application/<子系统名>" \
  --schema zgis \
  --sys <sys> \
  --major <major>
```

### 步骤5：格式化对齐

对更新后的全量脚本调用 `align_sql_values.py`。
