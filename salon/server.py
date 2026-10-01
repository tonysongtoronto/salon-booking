"""最小 HTTP 服务（只用标准库）：把 SalonService 暴露成两个 REST 接口。

POST /bookings                                   创建预约（API 1）
GET  /technicians/{id}/availability?date=&service_id=   查询可用时段（API 2）

时间一律按门店本地时间处理：带时区偏移的输入会被去掉偏移，只取墙上时间。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .booking import SalonService

SERVICE = SalonService()

STATUS = {
    "OK": 201,
    "UNKNOWN_TECHNICIAN": 404,
    "UNKNOWN_SERVICE": 404,
    "TECHNICIAN_CONFLICT": 409,
    "EQUIPMENT_CONFLICT": 409,
    "OUTSIDE_HOURS": 422,
}


def parse_local(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=None)


def error(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


def create_booking_response(svc: SalonService, body: dict, idem_key):
    try:
        tech, service, start = body["technician_id"], body["service_id"], parse_local(body["start_at"])
    except (KeyError, ValueError, TypeError):
        return 400, error("INVALID_REQUEST", "need technician_id, service_id, start_at (ISO 8601)")
    if not idem_key:
        return 400, error("MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")
    r = svc.create_booking(tech, service, start, idempotency_key=idem_key)
    if not r.ok:
        details = [{("equipment_id" if k == "equipment" else k): v for k, v in c.items()} for c in r.conflicts]
        return STATUS.get(r.code, 400), error(r.code, r.message, details)
    b = r.booking
    return 201, {
        "booking_id": b.id, "technician_id": b.technician, "service_id": b.service,
        "start_at": b.start.isoformat(), "end_at": b.end.isoformat(),
        "equipment": [{"equipment_id": n, "quantity": q} for n, q in b.equipment],
        "status": b.status,
    }


def availability_response(svc: SalonService, tech: str, query: dict):
    try:
        day = date.fromisoformat(query["date"][0])
        service = query["service_id"][0]
    except (KeyError, ValueError, IndexError):
        return 400, error("INVALID_REQUEST", "need date=YYYY-MM-DD and service_id")
    try:
        slots = svc.available_slots(tech, day, service)
    except KeyError:
        return 404, error("NOT_FOUND", "unknown technician or service")
    return 200, {
        "technician_id": tech, "date": day.isoformat(), "service_id": service,
        "duration_min": svc.services[service]["minutes"],
        "slots": [s.isoformat() for s in slots],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urlparse(self.path).path != "/bookings":
            return self._send(404, error("NOT_FOUND", "no such route"))
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, error("INVALID_REQUEST", "body is not valid JSON"))
        self._send(*create_booking_response(SERVICE, body, self.headers.get("Idempotency-Key")))

    def do_GET(self):
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "technicians" and parts[2] == "availability":
            return self._send(*availability_response(SERVICE, parts[1], parse_qs(url.query)))
        self._send(404, error("NOT_FOUND", "no such route"))


def main(port: int = 8000):
    print(f"Salon booking API on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
