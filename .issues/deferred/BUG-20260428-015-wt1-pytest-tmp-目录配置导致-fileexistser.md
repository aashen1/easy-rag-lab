---
id: BUG-20260428-015-wt1
title: pytest tmp 目录配置导致 FileExistsError
type: BUG
status: deferred
priority: medium
labels: []
assignee: null
milestone: null
created_at: '2026-04-28T00:48:30.972113'
updated_at: '2026-04-28T00:48:30.972113'
source: deferred\BUG-20260428-015-wt1-pytest-tmp-目录配置导致-fileexistser.md
legacy_id: BUG-017
---
## BUG 描述

pytest tmp 目录配置导致 FileExistsError

## 来源

TODO.md

## 备注

添加 tmp_path_retention_count=0 + pytest_configure 预清理；详见 [troubleshooting](troubleshooting/pytest-basetemp-fileexistserror.md)

## 迁移信息

- 原始 ID: BUG-017
- 迁移时间: 2026-04-28 00:48:30
