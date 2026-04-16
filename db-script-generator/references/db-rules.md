# 数据库脚本规范规则（V1.2）

本文件记录《数据库脚本规范 V1.2》下的核心规则与命名规范，适用于所有数据库脚本生成、检查、修复操作。

---

## 核心规则

### 规则1：`cx_fld` 永远不要配置 `id` 字段

- `id` 由数据库自增主键管理，不允许出现在 `cx_fld` 配置中。
- 所有生成脚本、修复脚本、增量变更脚本、数据库同步脚本必须强制排除 `id`。
- 一致性检查脚本必须将 `cx_fld` 中的 `id` 配置标记为 `[FORBIDDEN]`。

### 规则2：所有表必须有主键，主键名称为 `id`，默认自增

- **每个表必须包含 `id` 字段作为主键**。
- **非特殊指定时，`id` 设置为自增**：`id serial primary key`。
- **建表语句中**，`id` 的主键约束直接写在字段定义后面：`id serial primary key`。
- **禁止**在 `CREATE TABLE` 的字段列表末尾再写一行 `CONSTRAINT xxx PRIMARY KEY (id)`。

### 规则3：字段名小写（`act%` 表除外）

- `cx_fld` 中的 `colname` 必须为小写。
- 唯一例外：表名以 `act` 开头的表（历史兼容）。

### 规则4：`cx_fld.sys` 必须与 `cx_entity.sys` 保持一致

- 同一张表的 `cx_fld.sys` 和 `cx_entity.sys` 必须相同。
- 自动修复脚本应检测并同步该差异。

### 规则5：元数据与物理表必须一致

- `cx_entity` 中登记的表，必须在数据库 schema 中真实存在。
- `cx_fld` 中配置的字段，必须在对应的真实表中真实存在（孤儿字段必须清理）。
- 真实表中存在的非 `id` 字段，原则上应在 `cx_fld` 中有对应配置。

### 规则6：`id` 必须是主键

- 所有 `cx_entity` 登记的表，其 `id` 字段必须存在且必须是主键。
- 一致性检查脚本应标记 `[PK_ID]` 问题。

### 规则7：`cx_fld.isnum` 必须与字段实际类型一致

- **数值类型**：`integer`, `bigint`, `smallint`, `numeric`, `decimal`, `real`, `double precision`, `serial`, `bigserial`, `smallserial`
- `isnum = 1` 时，实际字段必须是数值类型。
- `isnum <> 1`（含 0 或空）时，实际字段不得是数值类型。
- 自动修复脚本应自动校正 `isnum` 值。

### 规则8：`disptype` 与 `cx_fldvalue` / 字段类型的一致性

- **`disptype = 2 或 6`**（下拉框/单选框）：必须在 `cx_fldvalue` 中存在对应字段的下拉值配置。缺失时标记为 `[DISPTYPE_FLDVALUE_MISSING]`。
- **`disptype = 3 或 5`**（日期/时间选择框）：实际字段类型必须是 `timestamp` 系列（`timestamp`, `timestamptz`, `timestamp without time zone`, `timestamp with time zone`）。
- **反向检查**：实际字段类型为 `timestamp` 系列时，`disptype` 必须是 `3` 或 `5`。否则自动修复脚本应将 `disptype` 修正为 `3`。

### 规则9：所有时间/日期类型统一使用 `timestamp`

- 数据库中禁止使用 `date`、`time`、`interval` 等非 `timestamp` 类型存储日期时间数据。
- 一致性检查脚本应将这类字段标记为 `[DATATYPE_TIMESTAMP_REQUIRED]`。

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

## 脚本行为约定

- **增量脚本幂等**：配置类增量脚本必须采用 `delete + INSERT` 模式，确保重复执行安全。
- **格式化对齐范围**：`align_sql_values.py` 默认只处理配置表 INSERT。禁止对大量业务数据表、日志表使用该脚本。
- **Excel 设计文档规范**：`id` 列的 `namec` 强制为 `ID`，且 `disporder=0, disptype=1, nullable=0, newedit=0, editable=0`。
