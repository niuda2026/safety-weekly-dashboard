# -*- coding: utf-8 -*-
"""从 M:\\下载 源文件重建周报 data/ 下 4 个履约明细 JSON（周度，与 _build_penalty_m.py 同源口径）。

背景（2026-10-04）：履约项目看板「履约达成处罚-周度」的汇总走 M盘直算（_build_penalty_m.py），
但弹窗明细（早会驳回/自检/督导/餐箱/装备）读的是周报看板 data/*.json（周报 Excel 管线产出，
每周要等周报上传才更新）→ 周中跑 M 盘更新时弹窗还是上周旧明细，与看板汇总对不上。
本脚本用本周 M 盘源文件直接重建，保证弹窗与看板同周同口径。

生成 4 个（health_violation.json 保持不动，与看板「健康证处罚金额=0」口径一致）：
  meeting_reject.json   <- _报备和日常早会驳回清单_*        （罚款：签到100/仪容仪表100/其余50，报备500）
  inspection_detail.json<- _【巡检平台站点检核】_子项检核明细查询_*（罚款同 _build_penalty_m.py：
      站长=自检100/项，整改不通过双倍200；督导=子项罚款表；健康证过期/证件不符按站人次分档300/400/500双倍；
      安全员行剔除、申诉通过行剔除——与看板聚合口径一致，保证弹窗=看板）
  disinfect_data.json   <- _餐箱消毒-违约金预计算_*          （12列直拷）
  equipment_detail.json <- _抽检不合格的骑手明细_*           （按早会文件名周窗口过滤，罚款：头盔200/服装100/餐箱100，盗版·其他平台150）

json 列布局与周报 Excel 管线（_gen_details_from_excel.py）产物一致，
周报看板 index.html 与履约项目看板弹窗按相同列号渲染，两边通用。

用法: python _gen_details_from_m.py [--dry-run]
"""
import os
import re
import sys
import glob
import json
import datetime
import shutil
import warnings

import openpyxl

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
M_DIR = r"M:\下载"
SERIAL_EPOCH = datetime.datetime(1899, 12, 30)

MEETING_FINE = {"签到": 100, "仪容仪表": 100}
MEETING_FINE_DEFAULT = 50
MEETING_BAOBEI_FINE = 500

CHECK_ITEM_FINE = [
    (["悬挂式灭火器"], 300),
    (["灭火器", "烟感"], 500),
    (["大功率电器", "高危火源"], 1000),
    (["易燃易爆", "电瓶"], 2000),
    (["视频监控", "流媒体", "站点环境", "门头", "灯箱", "看板海报",
      "充电区信息标识", "宿舍信息标识", "形象装备", "内容交流",
      "标准站建设"], 200),
    (["站点用电", "安全通道", "充电区选址", "毒面具"], 300),
]
CHECK_ITEM_DEFAULT = 200
HEALTH_EXPIRED_KEYS = ("回执单过期", "过期", "证件不符")

EQUIP_FINE = {"头盔": 200, "服装": 100, "餐箱": 100}
EQUIP_OTHER_PLATFORM_EXTRA = 50


def to_serial(dt):
    return int((dt - SERIAL_EPOCH).total_seconds() // 86400)


def week_sunday(dt):
    """该日期所在周的周日（周起点，Excel WEEK 起算习惯，与旧 json 一致）"""
    return dt - datetime.timedelta(days=(dt.weekday() + 1) % 7)


def ymd(v):
    """20260929 / 20260929.0 / '2026-09-29' -> date"""
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    s = str(v).strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return datetime.date(*map(int, m.groups()))
    return None


def num(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def find_newest(prefix):
    cands = [c for c in glob.glob(os.path.join(M_DIR, prefix + "*.xlsx"))
             if not os.path.basename(c).startswith("~$")]
    if not cands:
        raise FileNotFoundError("M盘找不到源文件: " + prefix)
    return max(cands, key=os.path.getmtime)


def read_sheet(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    idx = {h: i for i, h in enumerate(hdr)}
    rows = []
    for r in it:
        rows.append({h: (r[idx[h]] if idx[h] < len(r) else None) for h in hdr})
    wb.close()
    return rows


def backup(path):
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak_20261004_mgen")


def meeting_window():
    """从早会源文件名解析周窗口 (start_date, end_date)"""
    f = find_newest("_报备和日常早会驳回清单_")
    m = re.search(r"(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})", os.path.basename(f))
    if not m:
        raise ValueError("早会文件名无法解析窗口: " + f)
    a, b = datetime.date(*map(int, m.group(1).split("-"))), datetime.date(*map(int, m.group(2).split("-")))
    return f, a, b


# ── 1. 早会驳回 ────────────────────────────────────────────────
def gen_meeting(dry):
    src, w0, w1 = meeting_window()
    hdr = ["罚款金额", "日期", "周开始", "周次", "早会时间", "早会名称", "早会类型",
           "站点名称", "站点ID", "提交时间", "状态", "加盟区域", "城市", "加盟配送组",
           "大区", "加盟商ID", "加盟商名称", "审核不通过项目", "不通过标签明细",
           "审核不通过数量", "早会出勤率"] + [""] * 12
    out = [hdr]
    total = 0
    for r in read_sheet(src):
        if str(r.get("状态") or "") != "审核不通过":
            continue
        s = str(r.get("站点名称") or "").strip()
        if not s:
            continue
        d = ymd(r.get("早会时间")) or ymd(r.get("提交时间"))
        n = int(num(r.get("审核不通过数量")) or 1)
        typ = str(r.get("早会类型") or "")
        item = str(r.get("审核不通过项目") or "")
        if "报备" in typ:
            fine = MEETING_BAOBEI_FINE * n
        else:
            fine = next((v for k, v in MEETING_FINE.items() if k in item),
                        MEETING_FINE_DEFAULT) * n
        total += fine
        att = num(r.get("早会出勤率"))
        row = [
            fine,
            to_serial(datetime.datetime(d.year, d.month, d.day)) if d else "",
            to_serial(datetime.datetime.combine(week_sunday(d), datetime.time())) if d else "",
            "本周",
            int(num(r.get("早会时间"))) if num(r.get("早会时间")) else "",
            str(r.get("早会名称") or ""), typ, s,
            int(num(r.get("站点ID"))) if num(r.get("站点ID")) else "",
            str(r.get("提交时间") or ""), str(r.get("状态") or ""),
            str(r.get("加盟区域") or ""), str(r.get("城市") or ""),
            str(r.get("加盟配送组") or ""), str(r.get("大区") or ""),
            int(num(r.get("加盟商ID"))) if num(r.get("加盟商ID")) else "",
            str(r.get("加盟商名称") or ""), item,
            str(r.get("不通过标签明细") or ""),
            n, att,
        ] + [""] * 12
        out.append(row)
    print("[meeting_reject.json] %d 行, 罚款合计 %d (窗口 %s~%s)" % (len(out) - 1, total, w0, w1))
    if not dry:
        p = os.path.join(DATA_DIR, "meeting_reject.json")
        backup(p)
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


# ── 2. 站点检核（自检/督导） ───────────────────────────────────
def check_item_fine(item):
    it = re.sub(r"^\d+\.", "", str(item or "").strip())
    for keys, fine in CHECK_ITEM_FINE:
        if any(k in it for k in keys):
            return it, fine
    return it, CHECK_ITEM_DEFAULT


def gen_inspection(dry):
    src = find_newest("_【巡检平台站点检核】_子项检核明细查询_")
    rows = [r for r in read_sheet(src)
            if str(r.get("最终检核结果") or "") == "驳回"
            and str(r.get("申诉审核结果") or "") != "申诉通过"
            and "安全员" not in str(r.get("提交人岗位") or "")
            and str(r.get("站点名称") or "").strip()]
    # 健康证过期/证件不符 → 按站人次分档
    def is_health_tier(r):
        item = str(r.get("检核子项") or "")
        reason = str(r.get("质检原因") or "")
        return (("健康证" in item) or ("健康证" in reason)) and \
            any(k in reason for k in HEALTH_EXPIRED_KEYS)
    cnt = {}
    for r in rows:
        if is_health_tier(r):
            s = str(r.get("站点名称") or "").strip()
            cnt[s] = cnt.get(s, 0) + 1

    def fine_of(r):
        rect = str(r.get("整改审核结果") or "")
        dbl = 2 if ("不通过" in rect or "驳回" in rect) else 1
        if is_health_tier(r):
            s = str(r.get("站点名称") or "").strip()
            n = cnt[s]
            base = 300 if n <= 4 else (400 if n <= 9 else 500)
            return base * dbl
        pos = str(r.get("提交人岗位") or "")
        if pos == "站长":
            return 100 * dbl
        item, f = check_item_fine(r.get("检核子项"))
        if "健康证" in item:
            return 0   # 督导健康证（非过期类）金额待 T-1 源文件，与看板口径一致计 0
        return f * dbl

    hdr = ["日期", "大区名称", "区域名称", "配送组名称", "城市名称", "加盟商名称",
           "站点", "站点名称", "表单id", "检核类型", "提交人岗位", "检核子项",
           "最终检核结果", "得分", "配分", "巡检结果", "申诉审核结果", "检核结果",
           "复核结果", "质检结果", "质检原因", "质检备注", "整改审核结果", "辅助",
           "罚款", "督导罚款", "提交日期", "周开始", "周次"]
    out = [hdr]
    nf = ns = 0
    for r in rows:
        d = ymd(r.get("日期"))
        f = fine_of(r)
        pos = str(r.get("提交人岗位") or "")
        fine_self = f if pos == "站长" else ""
        fine_sup = "" if pos == "站长" else f
        if pos == "站长":
            nf += 1
        else:
            ns += 1
        vals = [r.get(k) for k in ["日期", "大区名称", "区域名称", "配送组名称", "城市名称",
                                   "加盟商名称", "站点", "站点名称", "表单id", "检核类型",
                                   "提交人岗位", "检核子项", "最终检核结果", "得分", "配分",
                                   "巡检结果", "申诉审核结果", "检核结果", "复核结果",
                                   "质检结果", "质检原因", "质检备注", "整改审核结果"]]
        vals = [int(v) if isinstance(v, float) and v.is_integer() else v for v in vals]
        row = vals + ["", fine_self, fine_sup,
                      to_serial(datetime.datetime(d.year, d.month, d.day)) if d else "",
                      to_serial(datetime.datetime.combine(week_sunday(d), datetime.time())) if d else "",
                      "本周"]
        out.append(row)
    print("[inspection_detail.json] %d 行 (自检 %d / 督导 %d)" % (len(out) - 1, nf, ns))
    if not dry:
        p = os.path.join(DATA_DIR, "inspection_detail.json")
        backup(p)
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


# ── 3. 餐箱消毒 ────────────────────────────────────────────────
def gen_disinfect(dry):
    src = find_newest("_餐箱消毒-违约金预计算_")
    keys = ["站点", "站点id", "城市", "区域", "大区", "标准化率不达标挡位",
            "因虚假消毒需要降低档位", "不安全违禁物违约金额", "标准化率",
            "标准化率不达标违约金额", "虚假消毒数", "不安全违禁物数"]
    out = [list(keys)]
    for r in read_sheet(src):
        s = str(r.get("站点") or "").strip()
        if not s:
            continue
        row = [r.get(k) if not isinstance(r.get(k), float) or not r.get(k).is_integer()
               else int(r[k]) for k in keys]
        # 虚假消毒数(idx10)口径（2026-10-05 用户确认）：源表计数列与降档列(idx6)
        # 可能不一致（如北戴河 计数0/降1挡），按降档兜底 max(计数,降档数)，与罚款对应
        try:
            row[10] = max(int(row[10] or 0), int(row[6] or 0))
        except (TypeError, ValueError):
            pass
        out.append(row)
    print("[disinfect_data.json] %d 行" % (len(out) - 1))
    if not dry:
        p = os.path.join(DATA_DIR, "disinfect_data.json")
        backup(p)
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


# ── 4. 装备抽检（按早会文件名周窗口过滤） ─────────────────────
def gen_equipment(dry, w0, w1):
    src = find_newest("_抽检不合格的骑手明细_")
    keys = ["天", "安全大区名称", "虚拟大区名称", "虚拟区域名称", "总加盟商名称",
            "加盟商名称", "配送城市", "配送城市名称", "运力管理线", "运力管理线名称",
            "加盟配送组名称", "配送站点", "配送站点名称", "骑手", "骑手名称",
            "是否服装检查骑手名称", "安全服装标签名称", "安全头盔标签名称",
            "安全餐箱标签名称", "安全骑手服装是否合格名称", "安全骑手头盔是否合格名称",
            "安全骑手餐箱是否合格名称", "安全服装是否申诉通过名称", "骑手服装标准化率",
            "罚款"]
    out = [list(keys)]
    kept = dropped = 0
    for r in read_sheet(src):
        day = ymd(r.get("天"))
        if day is None or not (w0 <= day <= w1):
            dropped += 1
            continue
        fine = 0
        for tag_key, part in (("安全头盔标签名称", "头盔"),
                              ("安全服装标签名称", "服装"),
                              ("安全餐箱标签名称", "餐箱")):
            tag = str(r.get(tag_key) or "")
            if "不合格" in tag or tag in ("盗版", "其他平台"):
                fine += EQUIP_FINE[part]
                if "盗版" in tag or "其他平台" in tag:
                    fine += EQUIP_OTHER_PLATFORM_EXTRA
        vals = [r.get(k) for k in keys[:-1]]
        vals = [int(v) if isinstance(v, float) and v.is_integer() else v for v in vals]
        out.append(vals + [fine])
        kept += 1
    print("[equipment_detail.json] %d 行 (窗口内 %d, 窗口外剔除 %d)" % (len(out) - 1, kept, dropped))
    if not dry:
        p = os.path.join(DATA_DIR, "equipment_detail.json")
        backup(p)
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out


def main():
    dry = "--dry-run" in sys.argv
    print("== 周报明细 JSON 重建（M盘源，%s）==" % ("dry-run" if dry else "写入"))
    gen_meeting(dry)
    gen_inspection(dry)
    gen_disinfect(dry)
    _src, w0, w1 = meeting_window()
    gen_equipment(dry, w0, w1)
    print("DONE")


if __name__ == "__main__":
    main()
