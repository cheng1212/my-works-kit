#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去AI味检查 —— 教学文案的去AI化机械尺（My-works 创作系统 · 第 2 步写文案后、第 9 步质检时用）

移植来源（novel-library-v2）：
  程序/工具/禁忌.py   词面维：点破句式、填充短语、系词回避、比喻密度、破折号密度、
                      「不是A而是B」、引号体系混用（5% 少数派规则）、繁体残留、中英夹杂、
                      半角标点定位、审阅档与反引号豁免——判据照搬
  程序/工具/指纹.py   结构维：三并列排比、同头排比（W2）、总结腔（W4A）、句长 CV、
                      拼接残留（重复片段）——正则照搬，阈值见 规则.json
  库/成文/卡片/写作工艺-AI 稿修订专项.md  修法 → 知识库/通用能力/写法/去AI味修订.md

为教学文案改了什么：
  ① 去掉只适用于小说的项（叙述黑名单「轻轻/缓缓」、裸称谓、计时拍、对白剥离等）；
  ② 新增 HARD「聊天残留」（以下是…/希望对你有所帮助…）与「AI 套话」；
     新增 WARN「教学空话」「空泛表扬」（逐字稿）、「加粗过密」；
  ③ 表格行、标题行、代码块、> 引用行（课标/教材原文）不进结构统计；> 引用行也不查词面；
  ④ 收 .md / .txt / .docx，也收目录（自动跳过源码、预览、审阅档）。

HARD 任一命中＝不可交付（退出码 1）；WARN 人工复核，不阻断（--严格 时 WARN 也判不过）。
词表与阈值真源＝同目录 规则.json，改规则不用改代码。

用法：
  python3 工具/去AI味/去AI味检查.py <文件或目录…> [--严格] [--报告 输出.md]
退出码：0=无 HARD；1=有 HARD（或 --严格 下有 WARN）；2=参数错
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
规 = json.load(io.open(os.path.join(HERE, "规则.json"), encoding="utf-8"))
阈 = 规["阈值"]
豁 = 规["豁免"]
文本后缀 = (".md", ".txt", ".docx")


# ---------------------------------------------------------------- 读文件
def 读docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    行 = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        行.append(t)
    import html
    return "\n".join(html.unescape(x) for x in 行)


def 读(path):
    if path.lower().endswith(".docx"):
        return 读docx(path)
    return io.open(path, encoding="utf-8", errors="replace").read()


def 收集(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in 豁["跳过目录"]]
                for f in sorted(files):
                    if f.lower().endswith(文本后缀) and not f.startswith("~$") and f != "README.md":
                        out.append(os.path.join(root, f))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print(f"✗ 路径不存在：{p}")
            sys.exit(2)
    # 同名 .md 与 .docx 并存时只查 .md（内容相同，避免双计）
    md = {os.path.splitext(x)[0] for x in out if x.endswith(".md")}
    return [x for x in out if not (x.endswith(".docx") and os.path.splitext(x)[0] in md)]


# ---------------------------------------------------------------- 工具
def 汉字数(t):
    return max(len(re.findall(r"[一-龥]", t)), 1)


def 定位(行列表, pat, 是正则=False, 上限=3):
    """返回 [(行号, 摘句)]。"""
    hits = []
    rx = re.compile(pat if 是正则 else re.escape(pat))
    for i, l in enumerate(行列表, 1):
        for m in rx.finditer(l):
            a = max(0, m.start() - 10)
            hits.append((i, l[a:m.end() + 10].strip()))
    return hits


def 摘(hits, n=3):
    return "；".join(f"L{i}「{s}」" for i, s in hits[:n])


def 正文行(行列表):
    """结构统计用：去掉标题、表格、引用、代码块、列表符号、空行。"""
    out, incode = [], False
    for l in 行列表:
        s = l.strip()
        if s.startswith("```"):
            incode = not incode
            continue
        if incode or not s or s.startswith(("#", "|", ">", "---", "<!--")):
            continue
        s = re.sub(r"^(?:[-*+]|\d+[.、）)])\s*", "", s)
        out.append(s)
    return out


# ---------------------------------------------------------------- 扫描
def 扫(path):
    t = 读(path)
    名 = os.path.basename(path)
    是docx = path.lower().endswith(".docx")
    原行 = t.splitlines()
    # 词面扫描行：去掉反引号提及、> 引用行（课标/教材原文）
    词行 = ["" if l.strip().startswith(">") else re.sub(r"`[^`\n]{1,40}`", "", l) for l in 原行]
    词文 = "\n".join(词行)
    字 = 汉字数(t)
    千 = lambda c: c * 1000.0 / 字
    hard, warn, info = [], [], []

    # ===== HARD =====
    for 段名 in ("HARD_聊天残留", "HARD_点破句式", "HARD_AI套话"):
        段 = 规[段名]
        for w in 段.get("词", []):
            h = 定位(词行, w)
            if h:
                hard.append(f"{段名[5:]}[{w}] ×{len(h)}：{摘(h)}")
        for rx in 段.get("正则", []):
            h = 定位(词行, rx, True)
            if h:
                hard.append(f"{段名[5:]}[{rx}] ×{len(h)}：{摘(h)}")

    # 引号体系混用（禁忌.py 5% 少数派规则）
    n直, n弯 = t.count("「"), t.count("“")
    if n直 and n弯:
        if min(n直, n弯) / (n直 + n弯) >= 阈["引号少数派占比"]:
            hard.append(f"引号体系混用（「」×{n直} 与 “”×{n弯}）——全篇统一一种")
        else:
            warn.append(f"引号疑似混用（少数体系 {min(n直, n弯)} 处）")

    # 繁体残留
    繁 = sorted({ch for ch in 规["繁体专用字形"] if ch in 词文})
    if 繁:
        hard.append(f"繁体字残留：{'、'.join(繁[:10])}")

    # docx 里的 markdown 残留
    if 是docx:
        h = 定位(原行, r"\*\*|^#{1,6}\s|^\s*[-*]\s\*\*", True)
        if h:
            hard.append(f"Markdown 符号残留（docx 里不该有 ** 或 #）×{len(h)}：{摘(h)}")

    # ===== WARN：按密度 =====
    for 段名 in ("WARN_教学空话", "WARN_总结腔", "WARN_系词回避", "WARN_比喻词"):
        段 = 规[段名]
        命 = []
        for w in 段["词"]:
            h = 定位(词行, w)
            if h:
                命.append((w, h))
        n = sum(len(h) for _w, h in 命)
        if n and 千(n) > 段["每千字上限"]:
            明细 = "、".join(f"{w}×{len(h)}" for w, h in 命[:8])
            首 = [x for _w, h in 命 for x in h][:2]
            warn.append(f"{段名[5:]} {n} 处（{千(n):.1f}/千字>{段['每千字上限']:g}）：{明细}　例：{摘(首, 2)}")

    段 = 规["WARN_空泛表扬"]
    命 = [(w, 定位(词行, w)) for w in 段["词"]]
    n = sum(len(h) for _w, h in 命)
    if n > 段["每篇上限"]:
        warn.append(f"空泛表扬 {n} 处（>{段['每篇上限']}）：{'、'.join(f'{w}×{len(h)}' for w, h in 命 if h)}——改成点评学生答案里的具体内容")

    # 不是A而是B（禁忌.py 口径）
    h = 定位(词行, r"不是[^，。\n]{1,12}，而是", True)
    if len(h) > 阈["不是A而是B_每篇"]:
        warn.append(f"「不是A而是B」×{len(h)}（>{阈['不是A而是B_每篇']}）：{摘(h)}")

    # ===== 结构维（只看正文行）=====
    正 = 正文行(词行)
    正文 = "".join(正)
    字正 = max(len(re.sub(r"\s", "", 正文)), 1)
    千正 = lambda c: c * 1000.0 / 字正

    n破 = 正文.count("——")
    if n破 and 千正(n破) > 阈["破折号_每千字"]:
        warn.append(f"破折号 {n破} 处（{千正(n破):.1f}/千字>1）——改成逗号、冒号或拆句")

    tri = re.findall(r"[^，。！？：；“”「」\n]{1,6}，[^，。！？：；“”「」\n]{1,6}，[^，。！？：；“”「」\n]{1,6}[，。]", 正文)
    if tri and 千正(len(tri)) > 阈["三并列排比_每千字"]:
        warn.append(f"三并列排比 {len(tri)} 处（{千正(len(tri)):.1f}/千字>{阈['三并列排比_每千字']:g}）：「{tri[0]}」")

    w2 = []
    for l in 正:
        m = re.search(r"([一-龥]{2,3})[一-龥]{0,8}[，、；]\s*\1[一-龥]{0,8}[，、；]\s*\1", l)
        if m:
            w2.append(m.group(0))
    if len(w2) > 阈["同头排比_每篇"]:
        warn.append(f"同头排比 {len(w2)} 处（>{阈['同头排比_每篇']}）：「{w2[0][:30]}」")

    if not 是docx:
        nb = len(re.findall(r"\*\*[^*\n]+\*\*", t))
        if nb and 千(nb) > 阈["加粗_每千字"]:
            warn.append(f"加粗过密 {nb} 处（{千(nb):.1f}/千字>{阈['加粗_每千字']:g}）——只留真正的重点")

    句 = re.findall(r"[^。！？\n]+[。！？]", 正文)
    长 = [len(re.sub(r"[，、；：“”「」‘’\s]", "", s)) for s in 句 if len(s.strip()) > 1]
    if len(长) >= 阈["句长CV_最少句数"]:
        mu = sum(长) / len(长)
        cv = (sum((x - mu) ** 2 for x in 长) / len(长)) ** 0.5 / mu if mu else 0
        info.append(f"句长 CV {cv:.2f}，均长 {mu:.0f} 字，{len(长)} 句")
        if cv < 阈["句长CV_下限"]:
            warn.append(f"句长太匀（CV {cv:.2f}<{阈['句长CV_下限']:g}）——长短句交替，别每句都一样长")

    # 拼接残留：≥N 字片段重复 ≥M 次（教案里目标在评价里复现是正常的，只抓高频）
    L, M = 阈["重复片段_字数"], 阈["重复片段_次数"]
    body = re.sub(r"\s", "", 正文)
    from collections import Counter
    c = Counter(body[i:i + L] for i in range(0, max(len(body) - L + 1, 0)))
    reps = [(g, k) for g, k in c.items() if k >= M and len(re.findall(r"[一-龥]", g)) >= L - 3]
    maximal = []
    for g, k in sorted(reps, key=lambda x: -x[1]):
        if not any(g[:8] in m for m, _k in maximal):
            maximal.append((g, k))
    if maximal:
        warn.append("复读片段（≥%d 字重复 ≥%d 次）：" % (L, M) + "；".join(f"「{g}」×{k}" for g, k in maximal[:3]))

    # 中英夹杂
    白 = {w.upper() for w in 规["中英白名单"]}
    英 = [m.group(0) for m in re.finditer(r"[A-Za-z][A-Za-z\-/]{2,}", 正文) if m.group(0).upper() not in 白]
    if 英:
        warn.append(f"中英夹杂 ×{len(英)}：{'、'.join(sorted(set(英))[:6])}（专有名词可加进 规则.json 白名单）")

    # 半角标点定位（人工项）
    半 = [(i, l) for i, l in enumerate(原行, 1) if re.search(r"[一-龥][,;:?!]|[,;:?!][一-龥]", l)]
    if 半:
        info.append(f"半角标点 {len(半)} 行（人工项）：" + "；".join(f"L{i}" for i, _l in 半[:6]))

    return 字, hard, warn, info


def main(argv):
    ap = argparse.ArgumentParser(description="去AI味检查（教学文案版）")
    ap.add_argument("路径", nargs="*")
    ap.add_argument("--契约", action="store_true", help="打印当前规则里的数（与《去AI味写前契约》核对）")
    ap.add_argument("--严格", action="store_true", help="WARN 也判不过")
    ap.add_argument("--报告", help="把结果另存为 markdown")
    a = ap.parse_args(argv[1:])
    if a.契约:
        for k, v in 规.items():
            if k.startswith(("HARD_", "WARN_")):
                线 = v.get("每千字上限", v.get("每篇上限"))
                print(f"{k}：" + (f"线 {线}｜" if 线 is not None else "一票否决｜") + "、".join(v.get("词", [])[:10]) + ("…" if len(v.get("词", [])) > 10 else ""))
        print("阈值：" + "；".join(f"{k}={v}" for k, v in 阈.items() if not k.startswith("_")))
        return 0
    if not a.路径:
        ap.error("请给出文件或目录")
    files = 收集(a.路径)
    if not files:
        print("✗ 没有找到 .md/.txt/.docx 文件")
        return 2
    out, 总hard, 总warn = [], 0, 0
    for f in files:
        名 = os.path.basename(f)
        if any(k in 名 for k in 豁["审阅档文件名"]):
            out.append(f"[审阅档] {f}——只报不判")
            continue
        字, hard, warn, info = 扫(f)
        总hard += bool(hard)
        总warn += bool(warn)
        tag = "FAIL" if hard else ("WARN" if warn else "PASS")
        out.append("=" * 60)
        out.append(f"[{tag}] {f}（{字} 字）")
        out += [f"  ✗ {h}" for h in hard]
        out += [f"  ! {w}" for w in warn]
        out += [f"  · {x}" for x in info]
    不过 = 总hard > 0 or (a.严格 and 总warn > 0)
    out.append("-" * 60)
    out.append(f"共 {len(files)} 份：HARD {总hard} 份，WARN {总warn} 份。⇒ "
               + ("不可交付：先按《去AI味修订》改掉 ✗ 项再重跑" if 不过 else "可交付（! 项请人工过一遍）"))
    text = "\n".join(out)
    print(text)
    if a.报告:
        io.open(a.报告, "w", encoding="utf-8").write("# 去AI味检查报告\n\n```text\n" + text + "\n```\n")
    return 1 if 不过 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
