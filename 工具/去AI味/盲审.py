#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盲审 —— 教学文案的无上下文冷读审核（My-works 创作系统 · 写后第二道）

移植来源：novel-library-v2 `程序/流程/盲审.py`（工序④＝闸序 1）。
v2 铁律原话：「机械闸之前必须由一个没有上下文的读者先看一遍」——写稿的那个上下文里，
大纲、卡、前文全在，它看见的每一句都是“应该的”，AI 味与硬伤在那个上下文里天然隐身。
只把成稿本身交给一个冷读者，它才会像真正的读者（教研员、听课老师）一样被绊住。

本程序是程序，盲审不是：审的人是一个**新开的、没有本次上下文的子代理**（或另一个模型、另一个人）。
程序只做两件配套的活：
  --派单 <文件>           出任务书（给什么、不给什么、看什么、审查单格式），会话照单派冷读者
  --记 <审查单> <文件>    收审查单：格式校验 → 归档到 <作品>/审核/<文件名>-盲审-<轮次>.md
                          → 记下被审文件的指纹（改过稿就要重审）→ FAIL 回去改
轮次上限 3：第 3 轮仍 FAIL 就停下报用户（v2 实测不设上限会跑到 10 轮）。

用法：
  python3 工具/去AI味/盲审.py --派单 06-xxx/02-教案/教案.md
  python3 工具/去AI味/盲审.py --记 审查单.md 06-xxx/02-教案/教案.md
退出码：0=PASS/WARN；1=FAIL 或格式不合规；2=参数错
"""
import argparse
import glob
import hashlib
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
上限轮次 = 3
语义六条 = ["目标可观察", "学情写这一班", "预设学生的错", "设计意图不套模板", "不凑数字排比", "原文未润色"]


def 作品目录(path):
    p = os.path.abspath(path)
    while p != os.path.dirname(p):
        if re.match(r"^\d{2}-", os.path.basename(p)) and os.path.isfile(os.path.join(os.path.dirname(p), "AGENTS.md")):
            return p
        p = os.path.dirname(p)
    return os.path.dirname(os.path.abspath(path))


def 指纹(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest()[:12]


def 审核目录(path):
    d = os.path.join(作品目录(path), "审核")
    os.makedirs(d, exist_ok=True)
    return d


def 已有轮次(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return sorted(glob.glob(os.path.join(审核目录(path), f"{stem}-盲审-*.md")))


def 任务书(path):
    名 = os.path.basename(path)
    return f"""# 盲审任务书：{名}

## 你是谁
你是一位没参与这份稿子写作的初中教研员，第一次读到它。你不知道它是怎么写出来的，也不需要知道。

## 给你什么
只有这份文件的正文（附在本任务书后面，或路径：{os.path.abspath(path)}）。

## 不给你什么（不要去找）
大纲、PPT、写作要求、知识库、课标文件、之前的对话。你看到的就是听课老师拿到的全部。

## 你要看什么
1. **AI标记**：具体哪句读起来像机器写的。摘原句，说为什么（套话、模板句、对举排比、数字凑整、空泛表扬、句式雷同、总结腔……）。
2. **AI特征**：整体读感上的机器痕迹（每格设计意图一个句式、学生活动一路顺利、学情放哪课都成立……）。
3. **硬伤**：前后矛盾；时间合计不对；目标、活动、评价对不上；学科知识错误；同一事物前后叫法不一。
4. **语义层六条**：逐条答“是/否”，“否”要摘原句。
   目标可观察｜学情写这一班｜预设学生的错｜设计意图不套模板｜不凑数字排比｜原文未润色
   （“原文未润色”指用 > 引用的课标、教材原文像不像被改写过；看不出就答“是”。）

## 怎么判
- FAIL：有硬伤；或六条里有 2 条及以上答“否”；或 AI标记 ≥5 处。
- WARN：有 AI标记或 1 条“否”，但不影响上课。
- PASS：读下来像一位老师为这节课写的。

## 审查单格式（严格照抄结构，否则视为未审）

```
判定：PASS / WARN / FAIL（三选一）
对象：{名}
## AI标记
- 「原句」｜为什么像机器：……
## AI特征
- ……
## 硬伤
- 「原句」｜问题：……   （没有就写“无”）
## 语义层六条
1. 目标可观察：是/否｜……
2. 学情写这一班：是/否｜……
3. 预设学生的错：是/否｜……
4. 设计意图不套模板：是/否｜……
5. 不凑数字排比：是/否｜……
6. 原文未润色：是/否｜……
```
"""


def 校验(单, 名):
    错 = []
    m = re.search(r"判定[:：]\s*(PASS|WARN|FAIL)\b", 单)
    if not m:
        错.append("缺“判定：PASS/WARN/FAIL”")
    if not re.search(r"对象[:：]\s*" + re.escape(名), 单):
        错.append(f"“对象：”不是 {名}（审错文件？）")
    for h in ("## AI标记", "## AI特征", "## 硬伤", "## 语义层六条"):
        if h not in 单:
            错.append(f"缺小节 {h}")
    否 = 0
    for k in 语义六条:
        mm = re.search(re.escape(k) + r"[:：]\s*(是|否)", 单)
        if not mm:
            错.append(f"语义层未答：{k}")
        elif mm.group(1) == "否":
            否 += 1
    判 = m.group(1) if m else None
    if 判 == "FAIL" and "「" not in 单:
        错.append("FAIL 必须摘原句作证据（「……」）")
    return 判, 否, 错


def main(argv):
    ap = argparse.ArgumentParser(description="盲审（教学文案版）")
    ap.add_argument("--派单", metavar="文件")
    ap.add_argument("--记", nargs=2, metavar=("审查单", "文件"))
    a = ap.parse_args(argv[1:])
    if a.派单:
        f = a.派单
        if not os.path.isfile(f):
            print(f"✗ 不存在：{f}"); return 2
        n = len(已有轮次(f)) + 1
        if n > 上限轮次:
            print(f"✗ 已审 {上限轮次} 轮，停下报用户，不再派单"); return 1
        out = os.path.join(审核目录(f), os.path.splitext(os.path.basename(f))[0] + f"-盲审任务书-{n}.md")
        io.open(out, "w", encoding="utf-8").write(任务书(f))
        print(任务书(f))
        print(f"\n（第 {n} 轮任务书已存：{out}。派一个**新开、无上下文**的子代理，只给它任务书和这份文件。）")
        return 0
    if a.记:
        单路径, f = a.记
        if not (os.path.isfile(单路径) and os.path.isfile(f)):
            print("✗ 审查单或被审文件不存在"); return 2
        单 = io.open(单路径, encoding="utf-8").read()
        判, 否, 错 = 校验(单, os.path.basename(f))
        if 错:
            print("✗ 审查单不合规，视为未审：\n  - " + "\n  - ".join(错)); return 1
        n = len(已有轮次(f)) + 1
        if n > 上限轮次:
            print(f"✗ 已满 {上限轮次} 轮，停下报用户"); return 1
        out = os.path.join(审核目录(f), os.path.splitext(os.path.basename(f))[0] + f"-盲审-{n}.md")
        头 = f"<!-- 被审文件：{os.path.relpath(f, 作品目录(f))}｜指纹：{指纹(f)}｜轮次：{n} -->\n"
        io.open(out, "w", encoding="utf-8").write(头 + 单)
        print(f"[{判}] 第 {n} 轮盲审已归档：{out}（语义层“否” {否} 条）")
        if 判 == "FAIL":
            print("⇒ 回去按审查单逐处改，改完重新机扫并派下一轮" + ("；已到第 3 轮，停下报用户" if n >= 上限轮次 else ""))
            return 1
        print("⇒ 盲审过。被审文件再改动就要重审（闸会比对指纹）")
        return 0
    ap.print_help(); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
