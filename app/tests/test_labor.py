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


class OvernightTest(unittest.TestCase):
    def P(self, at, kind):
        return {"at": at + ":00", "kind": kind}

    def test_night_market_shift(self):
        # 夜市：18:00 上班、隔天 02:00 下班 → 算在前一天、8 小時
        by = {"2026-03-02": [self.P("2026-03-02 18:00", "in")], "2026-03-03": [self.P("2026-03-03 02:00", "out"), self.P("2026-03-03 18:00", "in")],
              "2026-03-04": [self.P("2026-03-04 02:05", "out")]}
        st = P.stitch_overnight(by)
        segs = P.pair_day(st["2026-03-02"])[0]
        self.assertEqual(segs[0][2], 480)
        self.assertEqual(segs[0][1], "隔天 02:00")
        self.assertEqual(P.pair_day(st["2026-03-03"])[0][0][2], 485)
        self.assertNotIn("2026-03-04", st)

    def test_out_belongs_to_previous_month(self):
        st = P.stitch_overnight({"2026-04-01": [self.P("2026-04-01 01:30", "out")]}, before={"at": "2026-03-31 18:00:00", "kind": "in"})
        self.assertEqual(st, {})

    def test_last_day_of_month_night(self):
        st = P.stitch_overnight({"2026-03-31": [self.P("2026-03-31 22:00", "in")]}, after=[self.P("2026-04-01 06:00", "out")])
        self.assertEqual(P.pair_day(st["2026-03-31"])[0][0][2], 480)

    def test_too_far_apart_not_stitched(self):
        st = P.stitch_overnight({"2026-03-02": [self.P("2026-03-02 08:00", "in")], "2026-03-03": [self.P("2026-03-03 09:00", "out")]})
        self.assertTrue(P.pair_day(st["2026-03-02"])[2])     # 25 小時：不接，列成漏打卡

    def test_graveyard_shift_with_break_stays_one_day(self):
        # 大夜班 23:00–03:00、03:30–07:00：整班算在 3/2，不會變成 3/3 也上班（不會多算一個出勤日）
        by = {"2026-03-02": [self.P("2026-03-02 23:00", "in")],
              "2026-03-03": [self.P("2026-03-03 03:00", "out"), self.P("2026-03-03 03:30", "in"), self.P("2026-03-03 07:00", "out"),
                             self.P("2026-03-03 23:02", "in")],
              "2026-03-04": [self.P("2026-03-04 03:00", "out")]}
        st = P.stitch_overnight(by)
        s2 = P.pair_day(st["2026-03-02"])[0]
        self.assertEqual([x[2] for x in s2], [240, 210])
        self.assertEqual(s2[1][0], "隔天 03:30")
        self.assertEqual([p["at"][11:16] for p in st["2026-03-03"]], ["23:02", "03:00"])
        self.assertEqual(P.pair_day(st["2026-03-03"])[0][0][2], 238)
        self.assertEqual(P.break_flags("2026-03-02", s2), [])        # 中間休 30 分鐘：合法

    def test_break_check_handles_next_day(self):
        self.assertTrue(P.break_flags("2026-03-02", [("22:00", "隔天 06:00", 480)]))


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
