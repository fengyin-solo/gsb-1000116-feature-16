"""内审管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "audit"
REQUIRED_FIELDS = ["内审编号", "审核范围", "审核组长"]
STATUS_ORDER = ["计划中", "执行中", "已完成", "跟踪中"]
ACTION_RULES = {"开始内审": "执行中", "完成内审": "已完成", "跟踪验证": "跟踪中"}
NEGATIVE_ACTIONS: list[str] = []
# 列表接口单页上限：前端分页下拉与此保持一致，超过一律由路由层拒绝。
MAX_PAGE_SIZE = 200
# 状态展示列：列表里的「内审状态」必须和机器字段 status 同步，不能只改一边。
STATUS_FIELD = "内审状态"


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
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter(keyword=keyword, scope=scope, leader=leader, status=status)
        total = len(rows)
        # 路由层已经校验过范围，这里再兜底一次，保证直接调服务也不会拿到负页。
        page = max(page, 1)
        size = max(size, 1)
        start = (page - 1) * size
        return rows[start:start + size], total

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        scope: str | None = None,
        leader: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """导出不分页：按当前筛选条件返回全量，避免被单页上限截断。"""
        rows = self._filter(keyword=keyword, scope=scope, leader=leader, status=status)
        return rows, len(rows)

    def stats(self) -> dict[str, Any]:
        """数量指标：按状态统计内审记录，容忍记录缺 status 字段（计入未知）。"""
        rows = store.rows(MODULE)
        by_status = {status: 0 for status in STATUS_ORDER}
        unknown = 0
        for row in rows:
            status = row.get("status")
            if status in by_status:
                by_status[status] += 1
            else:
                unknown += 1
        return {
            "total": len(rows),
            "by_status": by_status,
            "unknown": unknown,
            "pending": sum(1 for row in rows if row.get("pending")),
            "abnormal": sum(1 for row in rows if row.get("abnormal")),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

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
        entry[STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"内审记录已{action}"

    def _filter(
        self,
        *,
        keyword: str | None = None,
        scope: str | None = None,
        leader: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("内审编号", ""))]
        if scope:
            rows = [row for row in rows if scope in str(row.get("审核范围", ""))]
        if leader:
            rows = [row for row in rows if leader in str(row.get("审核组长", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows
