"""美甲店预约系统（内存版）：API 1 创建预约，API 2 查询某天可用时段。

约定：时间区间左闭右开 [start, end)，首尾相接不算重叠。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from threading import Lock
from typing import Optional

DEFAULT_EQUIPMENT = {"uv_lamp": 2, "spa_machine": 1}
DEFAULT_SERVICES = {
    "basic_manicure": {"minutes": 30, "needs": {}},
    "gel_manicure": {"minutes": 60, "needs": {"uv_lamp": 1}},
    "gel_extension": {"minutes": 90, "needs": {"uv_lamp": 1}},
    "hand_spa": {"minutes": 60, "needs": {"spa_machine": 1}},
}
DEFAULT_TECHNICIANS = ("T1", "T2", "T3")


# ---------- 纯函数：区间工具 ----------
def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def peak_usage(usages: list[tuple[datetime, datetime, int]],
               win_start: datetime, win_end: datetime) -> int:
    """窗口 [win_start, win_end) 内设备同时占用数的最大值。

    占用数只会在某个预约开始的时刻上升，所以只需检查：窗口起点，
    以及窗口内每个已有预约的开始时刻（扫描线）。
    """
    points = {win_start} | {s for s, _, _ in usages if win_start < s < win_end}
    return max(
        (sum(q for s, e, q in usages if s <= p < e) for p in points),
        default=0,
    )


# ---------- 数据结构 ----------
@dataclass(frozen=True)
class Booking:
    id: str
    technician: str
    service: str
    start: datetime
    end: datetime
    equipment: tuple[tuple[str, int], ...]
    status: str = "confirmed"


@dataclass
class Result:
    ok: bool
    booking: Optional[Booking] = None
    code: str = "OK"  # OK / TECHNICIAN_CONFLICT / EQUIPMENT_CONFLICT / OUTSIDE_HOURS / UNKNOWN_*
    conflicts: list[dict] = field(default_factory=list)
    message: str = ""


class SalonService:
    def __init__(self, technicians=DEFAULT_TECHNICIANS, equipment=None, services=None,
                 open_time: time = time(9, 0), close_time: time = time(19, 0), step_min: int = 15):
        self.technicians = set(technicians)
        self.equipment = dict(equipment or DEFAULT_EQUIPMENT)
        self.services = dict(services or DEFAULT_SERVICES)
        self.open_time, self.close_time, self.step_min = open_time, close_time, step_min
        self._bookings: dict[str, Booking] = {}
        self._idem: dict[str, Result] = {}
        self._lock = Lock()  # 对应生产里的“事务 + 行锁”：检查与写入必须是一个原子步骤

    # ---------- 内部：冲突检查（API 1 和 API 2 共用，保证两个接口结论一致）----------
    def _active(self) -> list[Booking]:
        return [b for b in self._bookings.values() if b.status == "confirmed"]

    def _check(self, tech: str, service: str, start: datetime) -> Result:
        if tech not in self.technicians:
            return Result(False, code="UNKNOWN_TECHNICIAN", message=f"unknown technician {tech}")
        if service not in self.services:
            return Result(False, code="UNKNOWN_SERVICE", message=f"unknown service {service}")
        svc = self.services[service]
        end = start + timedelta(minutes=svc["minutes"])
        day = start.date()
        if start.time() < self.open_time or end > datetime.combine(day, self.close_time):
            return Result(False, code="OUTSIDE_HOURS", message="booking must end within business hours")

        active = self._active()
        conflicts: list[dict] = []

        # 1) 技师：任意重叠即冲突
        for b in active:
            if b.technician == tech and overlaps(start, end, b.start, b.end):
                conflicts.append({"type": "technician", "technician": tech, "booking_id": b.id})
                break

        # 2) 设备：窗口内任一时刻 已占用 + 本次需要 > 库存 即冲突
        for eq, need in svc["needs"].items():
            usages = [
                (b.start, b.end, q)
                for b in active if overlaps(start, end, b.start, b.end)
                for name, q in b.equipment if name == eq
            ]
            peak = peak_usage(usages, start, end)
            if peak + need > self.equipment[eq]:
                conflicts.append({"type": "equipment", "equipment": eq,
                                  "capacity": self.equipment[eq], "peak_in_use": peak, "needed": need})

        if conflicts:
            code = "TECHNICIAN_CONFLICT" if conflicts[0]["type"] == "technician" else "EQUIPMENT_CONFLICT"
            return Result(False, code=code, conflicts=conflicts, message="time slot not available")
        return Result(True)

    # ---------- API 1 ----------
    def create_booking(self, technician: str, service: str, start: datetime,
                       idempotency_key: Optional[str] = None) -> Result:
        with self._lock:
            if idempotency_key and idempotency_key in self._idem:
                return self._idem[idempotency_key]
            res = self._check(technician, service, start)
            if res.ok:
                svc = self.services[service]
                b = Booking(
                    id=uuid.uuid4().hex[:8], technician=technician, service=service,
                    start=start, end=start + timedelta(minutes=svc["minutes"]),
                    equipment=tuple(svc["needs"].items()),
                )
                self._bookings[b.id] = b
                res = Result(True, booking=b)
            if idempotency_key:
                self._idem[idempotency_key] = res
            return res

    def cancel_booking(self, booking_id: str) -> bool:
        with self._lock:
            b = self._bookings.get(booking_id)
            if not b or b.status != "confirmed":
                return False
            self._bookings[booking_id] = Booking(**{**b.__dict__, "status": "cancelled"})
            return True

    # ---------- API 2 ----------
    def available_slots(self, technician: str, day: date, service: str) -> list[datetime]:
        if technician not in self.technicians or service not in self.services:
            raise KeyError("unknown technician or service")
        minutes = self.services[service]["minutes"]
        t = datetime.combine(day, self.open_time)
        last = datetime.combine(day, self.close_time) - timedelta(minutes=minutes)
        out = []
        with self._lock:  # 一致的快照
            while t <= last:
                if self._check(technician, service, t).ok:
                    out.append(t)
                t += timedelta(minutes=self.step_min)
        return out
