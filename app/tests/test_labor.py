# -*- coding: utf-8 -*-
"""勞基法計薪單元測試：python -m unittest tests.test_labor（在 app/ 底下執行）"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import payroll as P  # noqa: E402

H8 = 480


class HourlyTest(unittest.TestCase):
    def test_normal_day_with_overtime(self):
        # 時薪 200，平日 9 小時：8 小時 1,600＋加班 1 小時 ×1.34＝268
        r = P.legal_pay("hourly", 200, 0, "2026-03", {"2026-03-02": 540})
        self.assertEqual(r["base_reg"], 1600)
        self.assertEqual(r["ot_pay"], 268)
        self.assertEqual(r["gross"], 1868)

    def test_overtime_second_tier(self):
        # 平日 11 小時：加班 3 小時＝2 小時 ×1.34＋1 小時 ×1.67
        r = P.legal_pay("hourly", 200, 0, "2026-03", {"2026-03-02": 660})
        self.assertEqual(r["ot_pay"], round(200 * (2 * 1.34 + 1 * 1.67)))

    def test_sixth_day_is_rest_day(self):
        # 週一～週六各 8 小時：第 6 天＝休息日，2 小時 ×1.34＋6 小時 ×1.67
        days = {"2026-03-%02d" % d: H8 for d in range(2, 8)}
        r = P.legal_pay("hourly", 200, 0, "2026-03", days)
        self.assertEqual(r["base_reg"], 200 * 8 * 5)
        self.assertEqual(r["rest_pay"], round(200 * (2 * 1.34 + 6 * 1.67)))
        self.assertEqual(r["detail"]["2026-03-07"], "rest")

    def test_seventh_day_flagged(self):
        days = {"2026-03-%02d" % d: H8 for d in range(2, 9)}
        r = P.legal_pay("hourly", 200, 0, "2026-03", days)
        self.assertEqual(r["detail"]["2026-03-08"], "regular_off")
        self.assertTrue(any("例假" in f for f in r["flags"]))

    def test_holiday_double(self):
        r = P.legal_pay("hourly", 200, 0, "2026-10", {"2026-10-10": H8})
        self.assertEqual(r["hol_pay"], 3200)
        self.assertEqual(r["base_reg"], 0)

    def test_week_crossing_month(self):
        # 2026-10-01 是週四；9/28–9/30 已上 3 天，10/1–10/3 再上 3 天 → 10/3（週六）是這週第 6 天＝休息日
        r = P.legal_pay("hourly", 200, 0, "2026-10", {"2026-10-01": H8, "2026-10-02": H8, "2026-10-03": H8},
                        prev_days=["2026-09-28", "2026-09-29", "2026-09-30"])
        self.assertEqual(r["detail"]["2026-10-03"], "rest")

    def test_min_wage_flag(self):
        r = P.legal_pay("hourly", 180, 0, "2026-03", {"2026-03-02": H8})
        self.assertTrue(any("基本工資" in f for f in r["flags"]))

    def test_over_12_hours_flag(self):
        r = P.legal_pay("hourly", 200, 0, "2026-03", {"2026-03-02": 750})
        self.assertTrue(any("12 小時" in f for f in r["flags"]))

    def test_no_late_penalty(self):
        # 只算實際分鐘：晚 10 分鐘＝少 10 分鐘工資，沒有其他罰扣
        r = P.legal_pay("hourly", 240, 0, "2026-03", {"2026-03-02": 470})
        self.assertEqual(r["gross"], 240 * 470 // 60)


class BreakTest(unittest.TestCase):
    def test_five_hours_straight_flagged(self):
        self.assertTrue(P.break_flags("2026-03-02", [("10:00", "15:00", 300)]))

    def test_four_hours_ok(self):
        self.assertEqual(P.break_flags("2026-03-02", [("10:00", "14:05", 245)]), [])

    def test_short_break_counts_as_continuous(self):
        # 中間只休 10 分鐘，不算休息：10:00–12:30＋12:40–14:30 是連續 270 分鐘
        self.assertTrue(P.break_flags("2026-03-02", [("10:00", "12:30", 150), ("12:40", "14:30", 110)]))

    def test_real_break_resets(self):
        self.assertEqual(P.break_flags("2026-03-02", [("09:00", "13:00", 240), ("14:00", "18:00", 240)]), [])


class MonthlyTest(unittest.TestCase):
    def test_full_month(self):
        # 2026-03 共 31 天、22 個平日；月休 9 天、沒有國定假日 → 應上班 22 天，全做滿＝全額月薪
        from datetime import date, timedelta
        days, d = {}, date(2026, 3, 1)
        while d.month == 3:
            if d.weekday() < 5:
                days[d.isoformat()] = H8
            d += timedelta(days=1)
        r = P.legal_pay("monthly", 30000, 9, "2026-03", days)
        self.assertEqual(r["need"], 22 * H8)
        self.assertTrue(r["full"])
        self.assertEqual(r["gross"], 30000)

    def test_too_few_days_off_flag(self):
        r = P.legal_pay("monthly", 30000, 4, "2026-03", {"2026-03-02": H8})
        self.assertTrue(any("一例一休" in f for f in r["flags"]))

    def test_partial_month_proportional(self):
        days = {"2026-03-%02d" % d: H8 for d in (2, 3, 4, 5, 6)}
        r = P.legal_pay("monthly", 30000, 9, "2026-03", days)
        self.assertEqual(r["base_reg"], 30000 * 5 * H8 // (22 * H8))

    def test_holiday_reduces_need_and_pays_extra(self):
        # 2026-10 有 10/10、10/25 兩天國定假日 → 應上班 31−8−2＝21 天；10/10 出勤另加給一倍＝30000÷240×8
        r = P.legal_pay("monthly", 30000, 8, "2026-10", {"2026-10-10": H8})
        self.assertEqual(r["need"], 21 * H8)
        self.assertEqual(r["hol_pay"], 1000)

    def test_monthly_overtime_rate(self):
        r = P.legal_pay("monthly", 36000, 8, "2026-03", {"2026-03-02": 540})
        self.assertEqual(r["ot_pay"], round(36000 / 240 * 1.34))

    def test_fixed(self):
        r = P.legal_pay("fixed", 45000, 8, "2026-03", {"2026-03-02": 700})
        self.assertEqual(r["gross"], 45000)


if __name__ == "__main__":
    unittest.main()
