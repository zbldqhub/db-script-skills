# Workflow：从 Excel 设计文档生成全量 SQL 脚本

## 触发条件

用户说"从 Excel 生成脚本"、"Excel 转 SQL"、"根据设计文档建表"、"按 Excel 出全量脚本"等。

## 需要收集的信息

1. **Excel 文件路径**（单个 `.xlsx` 文件，或包含多个 `.xlsx` 的目录）
2. **SQL 脚本输出目录**（通常是 `<project-root>/01-Application` 或某个子系统目录）
3. **sys 值**（用于 `cx_fld` 和 `cx_fldvalue`，默认 `0`）
4. 是否需要提供 `--entity-defaults`？
   - 如果项目对 `cx_entity` 有额外的必填列（超出 `name/namec/major/minor`），需要提供 JSON 文件
   - 否则使用默认值：`type=1, domains=1, glmaj=0, glmin=0, log=0`

## Excel 规范要求

- 每个表独占一个 sheet，sheet 名为表中文名（`namec`）
- 表头必须包含以下 16 列：
  `tabname`, `namec`, `colname`, `datatype`, `disporder`, `disptype`, `nullable`, `newedit`, `editable`, `indexname`, `indextype`, `indexcols`, `major_minor`, `reference`, `字典值`, `字段说明`
- `major_minor` 格式：`major@minor`，如 `41@1`
- `reference` 格式：`othertable(othercol)`
- `字典值` 格式：`0=正常; 1=停用`

## 执行步骤

### 步骤1：创建输出目录

```bash
mkdir "<output-dir>"
```

### 步骤2（可选）：准备 entity-defaults JSON

如果 `cx_entity` 需要额外默认值：

```json
{
  "type": "1",
  "domains": "1",
  "glmaj": "0",
  "glmin": "0",
  "log": "0"
}
```

### 步骤3：生成 SQL 脚本

```bash
python db-design-doc-generator/scripts/generate_sql_from_excel.py \
  --input "<project-root>/00-Design/01-Excel/design.xlsx" \
  --output-dir "<output-dir>" \
  --sys "0"
```

如需指定 entity defaults：

```bash
python db-design-doc-generator/scripts/generate_sql_from_excel.py \
  --input "<project-root>/00-Design/01-Excel/design.xlsx" \
  --output-dir "<output-dir>" \
  --sys "0" \
  --entity-defaults entity_defaults.json
```

### 步骤4：格式化对齐

对生成的 `02-cx_fld.sql` 和 `03-cx_fldvalue.sql` 进行中文宽度对齐：

```bash
python db-script-generator/scripts/align_sql_values.py --input "<output-dir>/02-cx_fld.sql"
python db-script-generator/scripts/align_sql_values.py --input "<output-dir>/03-cx_fldvalue.sql"
```

## 输出结果

- `01-table.sql`：CREATE TABLE、COMMENT ON COLUMN、外键约束
- `02-cx_fld.sql`：字段配置 INSERT
- `03-cx_fldvalue.sql`：字典值 INSERT
- `04-cx_entity.sql`：实体元数据 INSERT
- `05-index.sql`：索引 DROP / CREATE
