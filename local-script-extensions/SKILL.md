---
name: local-script-extensions
description: 在不连接数据库的情况下，根据 JSON 变更配置直接修改本地全量 SQL 脚本（01-table / 02-cx_fld / 03-cx_fldvalue）并在指定增量脚本末尾追加变更块。Use when the user wants to modify local SQL scripts without database access, or when applying quick schema changes directly to existing full-installation and upgrade scripts.
---

# 本地无库脚本同步扩展

本 Skill 提供单一脚本 `update_db_scripts.py`，全程不连接数据库，仅根据 JSON 配置修改本地全量脚本和增量脚本。

## 脚本能力清单

| 脚本 | 用途 | 自由度 |
|------|------|--------|
| `update_db_scripts.py` | 读取 JSON 配置，同步更新本地 `01-table.sql`、`02-cx_fld.sql`、`03-cx_fldvalue.sql` 及增量脚本 | 低 |

---

### `update_db_scripts.py`

```bash
python local-script-extensions/update_db_scripts.py --config changes.json
```

**参数：**
- `--config` / `-c`：JSON 配置文件路径（必需）

---

## 配置文件格式

```json
{
  "project_root": "..",
  "system": "19-热线服务系统",
  "target_upgrade": "02-Upgrade/update2026.sql",
  "author": "你的名字",
  "comment": "修正：删除 hl_notice 错误添加的字段",
  "changes": [
    {"action": "drop_columns", "table": "hl_notice", "columns": ["ggzt", "shzt"]},
    {"action": "add_columns", "table": "rn_public_msg", "columns": [
      {"name": "ggzt", "definition": "integer NOT NULL DEFAULT 0", "comment": "公告状态"}
    ]},
    {"action": "remove_fld", "table": "hl_notice", "columns": ["ggzt", "shzt"]},
    {"action": "add_fld", "table": "rn_public_msg", "sys": "19", "flds": [
      {"colname": "ggzt", "namec": "公告状态", "disptype": 2, "isnum": 1, "disporder": 9}
    ]},
    {"action": "remove_fldvalue", "table": "hl_notice", "columns": ["ggzt"]},
    {"action": "add_fldvalue", "table": "rn_public_msg", "sys": "19", "values": [
      {
        "colname": "ggzt",
        "items": [
          {"disporder": 1, "dbvalue": "0", "dispc": "停止"},
          {"disporder": 2, "dbvalue": "1", "dispc": "启用"}
        ]
      }
    ]}
  ]
}
```

**配置字段说明：**
- `project_root`：项目根目录（相对或绝对路径）
- `system`：子系统目录名（用于定位 `01-Application/<system>/`）
- `target_upgrade`：增量脚本相对路径（基于 `project_root`）
- `author`：作者名（写入增量脚本注释）
- `comment`：变更说明（写入增量脚本注释）
- `changes`：变更列表

**支持的 `action`：**

| action | 作用 |
|--------|------|
| `add_columns` | 在 `01-table.sql` 的目标表中添加字段及注释；增量生成 `ADD COLUMN` |
| `drop_columns` | 在 `01-table.sql` 的目标表中删除字段及注释；增量生成 `DROP COLUMN` |
| `add_fld` | 在 `02-cx_fld.sql` 中添加配置；增量生成 `delete + INSERT` |
| `remove_fld` | 在 `02-cx_fld.sql` 中删除配置；增量生成 `delete` |
| `add_fldvalue` | 在 `03-cx_fldvalue.sql` 中添加值域；增量生成 `delete + INSERT` |
| `remove_fldvalue` | 在 `03-cx_fldvalue.sql` 中删除值域；增量生成 `delete` |

---

## 核心规则

- `cx_fld` 中永远不要配置 `id` 字段。
- 增量脚本中的 `delete + INSERT` 模式确保重复执行幂等。
