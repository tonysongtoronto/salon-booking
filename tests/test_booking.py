import random
import unittest
from datetime import date, datetime, timedelta
from threading import Thread

from salon.booking import SalonService, overlaps, peak_usage

D = date(2026, 10, 2)


def at(h, m=0):
    return datetime(2026, 10, 2, h, m)


class IntervalTests(unittest.TestCase):
    def test_back_to_back_is_not_overlap(self):
        self.assertFalse(overlaps(at(10), at(11), at(11), at(12)))
        self.assertTrue(overlaps(at(10), at(11), at(10, 59), at(12)))

    def test_peak_usage_sweeps_every_start(self):
        usages = [(at(10), at(11, 30), 1), (at(11), at(12), 1)]
        self.assertEqual(peak_usage(usages, at(10, 30), at(11, 30)), 2)


class CreateBookingTests(unittest.TestCase):
    def setUp(self):
        self.s = SalonService()

    def test_success_computes_end_time(self):
        r = self.s.create_booking("T1", "gel_extension", at(10))
        self.assertTrue(r.ok)
        self.assertEqual(r.booking.end, at(11, 30))

    def test_technician_overlap_rejected_back_to_back_ok(self):
        self.assertTrue(self.s.create_booking("T1", "basic_manicure", at(10)).ok)
        r = self.s.create_booking("T1", "basic_manicure", at(10, 15))
        self.assertEqual(r.code, "TECHNICIAN_CONFLICT")
        self.assertTrue(self.s.create_booking("T1", "basic_manicure", at(10, 30)).ok)

    def test_third_uv_lamp_booking_rejected(self):
        self.assertTrue(self.s.create_booking("T1", "gel_manicure", at(10)).ok)
        self.assertTrue(self.s.create_booking("T2", "gel_manicure", at(10)).ok)
        r = self.s.create_booking("T3", "gel_manicure", at(10))
        self.assertEqual(r.code, "EQUIPMENT_CONFLICT")
        self.assertEqual(r.conflicts[0]["equipment"], "uv_lamp")

    def test_every_moment_not_just_start_moment(self):
        # 10:30 开始时只有 1 盏灯在用，但 11:00 起第二单会让灯数到 2 → 新单会在 11:00–11:30 超限
        self.assertTrue(self.s.create_booking("T1", "gel_extension", at(10)).ok)      # 10:00–11:30
        self.assertTrue(self.s.create_booking("T2", "gel_manicure", at(11)).ok)       # 11:00–12:00
        r = self.s.create_booking("T3", "gel_manicure", at(10, 30))                   # 10:30–11:30
        self.assertEqual(r.code, "EQUIPMENT_CONFLICT")
        self.assertEqual(r.conflicts[0]["peak_in_use"], 2)

    def test_equipment_released_at_end_boundary(self):
        self.assertTrue(self.s.create_booking("T1", "gel_manicure", at(10)).ok)
        self.assertTrue(self.s.create_booking("T2", "gel_manicure", at(10)).ok)
        self.assertTrue(self.s.create_booking("T3", "gel_manicure", at(11)).ok)

    def test_spa_machine_capacity_one(self):
        self.assertTrue(self.s.create_booking("T1", "hand_spa", at(10)).ok)
        r = self.s.create_booking("T2", "hand_spa", at(10, 30))
        self.assertEqual(r.conflicts[0]["equipment"], "spa_machine")

    def test_no_equipment_service_ignores_saturated_lamps(self):
        self.s.create_booking("T1", "gel_manicure", at(10))
        self.s.create_booking("T2", "gel_manicure", at(10))
        self.assertTrue(self.s.create_booking("T3", "basic_manicure", at(10)).ok)

    def test_both_conflicts_reported_technician_first(self):
        self.s.create_booking("T1", "gel_manicure", at(10))
        self.s.create_booking("T2", "gel_manicure", at(10))
        r = self.s.create_booking("T1", "gel_manicure", at(10, 30))
        self.assertEqual(r.code, "TECHNICIAN_CONFLICT")
        self.assertEqual([c["type"] for c in r.conflicts], ["technician", "equipment"])

    def test_outside_business_hours(self):
        self.assertEqual(self.s.create_booking("T1", "gel_manicure", at(18, 30)).code, "OUTSIDE_HOURS")
        self.assertTrue(self.s.create_booking("T1", "gel_manicure", at(18)).ok)
        self.assertEqual(self.s.create_booking("T2", "basic_manicure", at(8, 45)).code, "OUTSIDE_HOURS")

    def test_unknown_ids(self):
        self.assertEqual(self.s.create_booking("T9", "gel_manicure", at(10)).code, "UNKNOWN_TECHNICIAN")
        self.assertEqual(self.s.create_booking("T1", "nope", at(10)).code, "UNKNOWN_SERVICE")

    def test_idempotency_key_returns_same_booking(self):
        a = self.s.create_booking("T1", "gel_manicure", at(10), idempotency_key="k1")
        b = self.s.create_booking("T1", "gel_manicure", at(10), idempotency_key="k1")
        self.assertTrue(a.ok and b.ok)
        self.assertEqual(a.booking.id, b.booking.id)
        self.assertEqual(len(self.s._active()), 1)

    def test_cancel_releases_technician_and_equipment(self):
        a = self.s.create_booking("T1", "gel_manicure", at(10))
        self.s.create_booking("T2", "gel_manicure", at(10))
        self.assertFalse(self.s.create_booking("T3", "gel_manicure", at(10)).ok)
        self.assertTrue(self.s.cancel_booking(a.booking.id))
        self.assertTrue(self.s.create_booking("T3", "gel_manicure", at(10)).ok)
        self.assertTrue(self.s.create_booking("T1", "basic_manicure", at(10)).ok)


class AvailableSlotsTests(unittest.TestCase):
    def setUp(self):
        self.s = SalonService()

    def test_empty_day_counts(self):
        self.assertEqual(len(self.s.available_slots("T1", D, "gel_manicure")), 37)   # 09:00–18:00
        self.assertEqual(len(self.s.available_slots("T1", D, "basic_manicure")), 39)  # 09:00–18:30
        self.assertEqual(self.s.available_slots("T1", D, "gel_manicure")[-1], at(18))

    def test_technician_schedule_excluded(self):
        self.s.create_booking("T1", "basic_manicure", at(10))
        slots = self.s.available_slots("T1", D, "basic_manicure")
        self.assertNotIn(at(10), slots)
        self.assertNotIn(at(10, 15), slots)
        self.assertIn(at(9, 30), slots)
        self.assertIn(at(10, 30), slots)

    def test_equipment_contention_excluded_for_free_technician(self):
        self.s.create_booking("T2", "gel_manicure", at(10))
        self.s.create_booking("T3", "gel_manicure", at(10))
        slots = self.s.available_slots("T1", D, "gel_manicure")
        self.assertIn(at(9), slots)            # 09:00–10:00 刚好在灯被占用前结束
        for m in (15, 30, 45):
            self.assertNotIn(at(9, m), slots)  # 与 10:00 起的两盏灯重叠
        for m in (0, 15, 30, 45):
            self.assertNotIn(at(10, m), slots)
        self.assertIn(at(11), slots)

    def test_slots_consistent_with_create(self):
        """随机预约若干单；之后对每个候选起点，API 2 的结论必须等于 API 1 的实际结果。"""
        rng = random.Random(7)
        names = list(self.s.services)
        for _ in range(25):
            t = at(9) + timedelta(minutes=15 * rng.randrange(0, 36))
            self.s.create_booking(rng.choice(["T1", "T2", "T3"]), rng.choice(names), t)
        for tech in ("T1", "T2", "T3"):
            for svc in names:
                slots = set(self.s.available_slots(tech, D, svc))
                t = at(9)
                while t < at(19):
                    probe = SalonService()
                    probe._bookings = dict(self.s._bookings)
                    ok = probe.create_booking(tech, svc, t).ok
                    self.assertEqual(ok, t in slots, (tech, svc, t))
                    t += timedelta(minutes=15)


class ConcurrencyTests(unittest.TestCase):
    def test_no_oversell_under_concurrent_requests(self):
        techs = [f"T{i}" for i in range(20)]
        s = SalonService(technicians=techs)
        results = []

        def go(t):
            results.append(s.create_booking(t, "gel_manicure", at(10)).ok)

        threads = [Thread(target=go, args=(t,)) for t in techs]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(results), 2)  # uv_lamp 只有 2 盏

    def test_same_technician_same_slot_only_one_wins(self):
        s = SalonService()
        results = []
        threads = [Thread(target=lambda: results.append(s.create_booking("T1", "basic_manicure", at(10)).ok))
                   for _ in range(30)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(results), 1)


if __name__ == "__main__":
    unittest.main()
