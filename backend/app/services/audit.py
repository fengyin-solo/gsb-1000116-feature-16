"""内审管理业务规则：状态流转、字段校验、筛选口径与数量汇总都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "audit"
REQUIRED_FIELDS = ["内审编号", "审核范围", "审核组长"]
STATUS_ORDER = ["计划中", "执行中", "已完成", "跟踪中"]
ACTION_RULES = {"开始内审": "执行中", "完成内审": "已完成", "跟踪验证": "跟踪中"}
NEGATIVE_ACTIONS = []

# 统计卡片口径：卡片名称 -> 需要计入的内审状态
SUMMARY_LABELS = {
    "计划内审": ["计划中"],
    "进行中内审": ["执行中"],
    "待跟踪内审": ["已完成", "跟踪中"],
}
SUMMARY_KEYS = list(SUMMARY_LABELS)


def _clean(value: Any) -> str:
    """把任意来源的字段值归一成去掉首尾空白的字符串，None / 非字符串都不会抛异常。"""
    if value is None:
        return ""
    return str(value).strip()


class AuditService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        scope: str | None = None,
        leader: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        """按编号 / 审核范围 / 组长 / 状态筛选，返回当前页记录、总量与状态汇总。

        汇总始终面向全部内审记录（与筛选条件无关），这样首次无记录、
        筛选结果为空或重试恢复时，数量指标口径都保持一致，不会随列表
        一起变成 0 而被误读成“没数据 / 加载失败”。
        """
        keyword = _clean(keyword)
        scope = _clean(scope)
        leader = _clean(leader)
        status = _clean(status)

        matched = [
            row for row in store.rows(MODULE)
            if (not keyword or keyword in _clean(row.get("内审编号")))
            and (not scope or scope in _clean(row.get("审核范围")))
            and (not leader or leader in _clean(row.get("审核组长")))
            and (not status or _clean(row.get("status")) == status)
        ]
        total = len(matched)
        start = max(page - 1, 0) * size
        items = [self._to_view(row) for row in matched[start:start + size]]
        return items, total, self.summarize()

    def summarize(self, rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
        """按状态口径汇总数量；状态缺失或非法的记录不计入任何卡片。"""
        if rows is None:
            rows = store.rows(MODULE)
        summary = {key: 0 for key in SUMMARY_KEYS}
        for row in rows:
            status = _clean(row.get("status"))
            for key, targets in SUMMARY_LABELS.items():
                if status in targets:
                    summary[key] += 1
        return summary

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._to_view(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: _clean(values.get(field)) for field in REQUIRED_FIELDS})
        # 其余字段允许暂缺，但落库时统一成字符串，避免列表渲染出现结构异常
        for field in ("审核日期", "不符合项", "纠正期限", "跟踪验证"):
            entry[field] = _clean(values.get(field))
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["内审状态"] = entry["status"]
        rows.append(entry)
        return self._to_view(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"内审记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内审管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        # 展示字段与流转状态同步，避免列表上的“内审状态”停留在旧批次
        entry["内审状态"] = target
        return self._to_view(entry), f"内审记录已{action}"

    def _to_view(self, row: dict[str, Any]) -> dict[str, Any]:
        """输出给前端的行视图：补齐展示字段并标记字段是否完整。

        旧数据 / 手工构造的异常数据可能缺列或状态非法，这里不抛错，
        而是用空串占位并通过 incomplete 告知前端“字段不完整”的原因。
        """
        view = dict(row)
        status = _clean(view.get("status"))
        if status not in STATUS_ORDER:
            status = ""
        view["status"] = status
        # 列表上的“内审状态”列始终以流转状态为准，避免旧数据里的占位文案与真实状态脱节
        view["内审状态"] = status
        missing = [field for field in REQUIRED_FIELDS if not _clean(view.get(field))]
        if not status:
            missing.append("内审状态")
        view["incomplete"] = bool(missing)
        view["missing_fields"] = missing
        return view
