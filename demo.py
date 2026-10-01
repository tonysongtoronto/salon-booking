"""演示：不启动服务，直接调用两个函数。运行：python demo.py"""
from datetime import date, datetime

from salon.booking import SalonService

s = SalonService()
d = lambda h, m=0: datetime(2026, 10, 2, h, m)

print("1) T1 约凝胶美甲 10:00 ->", s.create_booking("T1", "gel_manicure", d(10)).code)
print("2) T2 约凝胶美甲 10:00 ->", s.create_booking("T2", "gel_manicure", d(10)).code)
r = s.create_booking("T3", "gel_manicure", d(10))
print("3) T3 约凝胶美甲 10:00 ->", r.code, r.conflicts)

slots = s.available_slots("T3", date(2026, 10, 2), "gel_manicure")
print("4) T3 当天凝胶美甲可约起点（前 8 个）:", [t.strftime("%H:%M") for t in slots[:8]])
print("   其中包含 09:00、不含 09:15~10:45、含 11:00:",
      d(9) in slots, d(9, 15) not in slots, d(10, 45) not in slots, d(11) in slots)
