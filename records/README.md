# 执行记录使用说明

每道已执行题目放在 `records/<case_id>/`，必须包含 `record.json` 和 `screenshots/`。不要复制空目录冒充结果；开始执行时用初始化命令创建。

## F 每日操作

```powershell
# 为某题创建记录（不会写入 API Key）
uv run python scripts/manage_test_records.py init-record ms_008 --executor F

# 校验题库与所有已有记录，并更新进度/统计
uv run python scripts/manage_test_records.py all

# Day6-8 合并收尾的严格验收：未执行、未复核或验收线不达标都会返回失败
uv run python scripts/manage_test_records.py all --strict
```

## 状态口径

- `未执行`：没有 `record.json`，或记录没有 `executed_at`。
- `已执行`：有执行时间，但还没有合法判定。
- `已判定`：判定合法，尚未填写复核人和复核时间。
- `已复核`：判定合法，且 `reviewer`、`reviewed_at` 均已填写。

## 截图口径

- 每道题至少 4 张：`01_input`（输入问题）→ `02_progress`（运行阶段/检索进度）→ `03_package`（数据包结果）→ `04_validation`（校验/验证）。
- FAIL 必须额外包含报错截图 `05_error.png`。
- `record.json` 中的截图路径必须真实存在，建议命名 `NN_<stage>.png`。

## 判定口径

- `PASS`：包完整、无 ERROR、达到最少文件数、需要运行验证的格式已通过，且没有降级。
- `PASS_WITH_FALLBACK`：包可用且降级被明确记录；`is_fallback`/`quality=fallback`、原因和 manifest 证据必须可追溯。
- `FAIL`：无可用包、崩溃、ERROR、内容错误、运行验证失败或静默降级；必须填写 P1-P8 分类和失败原因。

`_management/progress.csv`、`quality_report.json` 和 `statistics_summary.md` 由脚本生成，不要手工改统计值。F 每日在 `_management/` 下查看统计，向团队同步进度。

## 记录字段约定

- `observations.retrieve[]` 每项结构见 `_templates/retrieve_item.example.json`：`req_id` 必填；`req_type`/`source`/`quality`/`status`/`format` 必须用代码枚举小写值；检索未成功必须填 `error`，降级必须填 `fallback_reason` 且 `is_fallback=true` 或 `quality=fallback`。
- `env` 只记录模型名与接口地址，不得填写 API Key。
