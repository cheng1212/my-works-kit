#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去AI味闸 —— 写后总闸：机扫 HARD 为 0 ＋ 每份教学文案都有一份对得上的盲审结论

移植来源：novel-library-v2 `程序/流程/机械闸.py`（“先查盲审结论，再跑机械尺”，台账留痕）。
本库简化为一个命令，第 2 步写完文案、第 9 步质检时都跑它；不过不许往下走。

查哪些文件：作品文件夹下 01–07、11 号子文件夹里的 .md/.txt（同名 docx 不重复查；
docx 另做 Markdown 残留检查）。也可以直接给文件。

判定：
  ① 去AI味检查.py 无 HARD；
  ② 审核/<文件名>-盲审-<最新轮>.md 存在，判定 PASS/WARN，且记录的指纹＝文件当前指纹
     （改过稿没重审＝不过）。
结果写入 <作品>/审核/去AI味闸.md。

用法：python3 工具/去AI味/闸.py <作品文件夹或文件…>
退出码：0=过；1=不过；2=参数错
"""
import glob
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util
spec = importlib.util.spec_from_file_location("盲审", os.path.join(HERE, "盲审.py"))
盲审 = importlib.util.module_from_spec(spec); spec.loader.exec_module(盲审)
文案目录 = re.compile(r"^(0[1-7]|11)-")


def 收集(args):
    out = []
    for p in args:
        if os.path.isfile(p):
            out.append(p)
        elif os.path.isdir(p):
            for d in sorted(os.listdir(p)):
                full = os.path.join(p, d)
                if os.path.isdir(full) and 文案目录.match(d):
                    for f in sorted(glob.glob(os.path.join(full, "**", "*"), recursive=True)):
                        if f.endswith((".md", ".txt")):
                            out.append(f)
        else:
            print(f"✗ 不存在：{p}"); sys.exit(2)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    files = 收集(argv[1:])
    if not files:
        print("✗ 没找到教学文案（01–07、11 号文件夹里的 .md/.txt）"); return 1
    行, 不过 = [], 0
    for f in files:
        docx = os.path.splitext(f)[0] + ".docx"
        扫 = [f] + ([docx] if os.path.isfile(docx) else [])
        r = subprocess.run([sys.executable, os.path.join(HERE, "去AI味检查.py")] + 扫, capture_output=True, text=True)
        机 = "过" if r.returncode == 0 else "HARD 未清"
        轮 = 盲审.已有轮次(f)
        if not 轮:
            盲 = "未盲审"
        else:
            last = io.open(轮[-1], encoding="utf-8").read()
            m = re.search(r"指纹：(\w+)", last); j = re.search(r"判定[:：]\s*(PASS|WARN|FAIL)", last)
            if not (m and j):
                盲 = "审查单损坏"
            elif m.group(1) != 盲审.指纹(f):
                盲 = f"稿子改过，需重审（上次第 {len(轮)} 轮 {j.group(1)}）"
            elif j.group(1) == "FAIL":
                盲 = f"第 {len(轮)} 轮 FAIL"
            else:
                盲 = f"第 {len(轮)} 轮 {j.group(1)}"
        ok = 机 == "过" and re.match(r"第 \d+ 轮 (PASS|WARN)$", 盲)
        不过 += not ok
        行.append(f"| {os.path.relpath(f)} | {机} | {盲} | {'✅' if ok else '❌'} |")
    表 = "| 文件 | 机扫 | 盲审 | 结论 |\n|---|---|---|---|\n" + "\n".join(行)
    结论 = "过" if not 不过 else f"不过（{不过} 份）"
    print(表 + f"\n\n去AI味闸：{结论}")
    for p in argv[1:]:
        if os.path.isdir(p):
            d = os.path.join(p, "审核"); os.makedirs(d, exist_ok=True)
            io.open(os.path.join(d, "去AI味闸.md"), "w", encoding="utf-8").write(f"# 去AI味闸\n\n{表}\n\n结论：**{结论}**\n")
    return 0 if not 不过 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
