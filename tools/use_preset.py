# -*- coding: utf-8 -*-
"""套用產業範本：把 presets/<產業>/ 的設定複製成你自己的設定檔。

用法：
  python tools/use_preset.py              # 列出所有範本
  python tools/use_preset.py drink        # 套用飲料店範本
  python tools/use_preset.py drink --force  # 已經有設定檔也覆蓋（會先備份成 .bak-日期時間）

會產生：
  config/store.toml   店家設定（店名、支出類別、功能開關……）
  data/ledger.toml    股東帳務設定（股東、期初、單位成本……）
已經存在的檔案預設不會覆蓋。
"""
import datetime
import os
import shutil
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESETS = os.path.join(ROOT, "presets")
TARGETS = {"store.toml": os.path.join(ROOT, "config", "store.toml"), "ledger.toml": os.path.join(ROOT, "data", "ledger.toml")}


def presets():
    out = []
    for k in sorted(os.listdir(PRESETS)):
        f = os.path.join(PRESETS, k, "store.toml")
        if os.path.isfile(f):
            with open(f, encoding="utf-8") as fh:
                title = fh.readline().replace("# 產業範本：", "").strip()
            out.append((k, title))
    return out


def apply(key, force=False):
    src_dir = os.path.join(PRESETS, key)
    if not os.path.isdir(src_dir):
        raise SystemExit("沒有這個範本：%s。可用的：%s" % (key, "、".join(k for k, _ in presets())))
    done = []
    for name, dst in TARGETS.items():
        src = os.path.join(src_dir, name)
        with open(src, "rb") as f:
            tomllib.load(f)                      # 先確認格式正確
        if os.path.exists(dst):
            if not force:
                done.append("略過 %s（已經存在；要覆蓋請加 --force）" % os.path.relpath(dst, ROOT))
                continue
            bak = dst + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            shutil.copyfile(dst, bak)
            done.append("備份 %s → %s" % (os.path.relpath(dst, ROOT), os.path.basename(bak)))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        done.append("建立 %s" % os.path.relpath(dst, ROOT))
    return done


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("可用的產業範本：")
        for k, t in presets():
            print("  %-10s %s" % (k, t))
        print("\n用法：python tools/use_preset.py <範本代號>")
        sys.exit(0)
    for line in apply(args[0], force="--force" in sys.argv):
        print(line)
    print("完成。接著把 config/store.toml 的店名、地址、電話改成你自己的；想先看示範畫面可以跑 python app/seed_demo.py --preset %s" % args[0])
