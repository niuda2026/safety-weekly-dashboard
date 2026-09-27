# -*- coding: utf-8 -*-
"""从《安全权益履约周报数据（9月）(1).xlsx》生成周报看板 data/compliance.json 与 data/accident.json
- 两表头部为双行（行0/行1），数据从行2开始
- compliance: Excel 履约类数据看板 A-R(18列) 与现有 schema 按位置 1:1 对齐
- accident : Excel 安全事故看板 A-O(15列)，取前14列(丢甲方预计处罚单均支出)，与现有 schema 按位置 1:1 对齐
- 数值保持数值；空单元格->""；Excel 错误值(#REF! 等)->""；整型浮点->int
"""
import openpyxl, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')

SRC = r"C:\Users\牛艳朝\Desktop\安全权益履约周报数据（9月） (1).xlsx"
OUT = r"C:\Users\牛艳朝\WorkBuddy\2026-09-04-04-42-17\safety-weekly-dashboard\data"

COMPLIANCE_HDR = ["大区","分区","区域","甲方预计总罚款","早会驳回数","早会罚款","自检驳回","自检罚款",
                  "督导驳回","督导罚款","标准化率","标准化不达标罚款","虚假消毒数","虚假消毒罚款",
                  "装备不合格数","装备罚款","装备合规率","健康证处罚金额"]
ACCIDENT_HDR = ["大区","分区","区域","上报保险数","小额事故数","公司承担","骑手承担","工单迟报数",
                "迟报罚款","保险超时数","超时罚款","上周完成单量","百万单事故数","小额赔付单均"]

def clean(v):
    if v is None:
        return ""
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return ""
        if s.startswith("#"):   # #REF! / #DIV! / #N/A 等错误值
            return ""
        return s
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        return v
    return v

def row_is_empty(row, ncols):
    return all((row[i] is None or (isinstance(row[i], str) and row[i].strip() == "")) for i in range(ncols))

def scan_errors(ws, ncols):
    errs = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 2:
            continue
        for j in range(min(ncols, len(row))):
            v = row[j]
            if isinstance(v, str) and v.strip().startswith("#"):
                errs.append((i+1, j+1, v))
    return errs

def convert(sheet_name, ncols, hdr):
    ws = wb[sheet_name]
    errs = scan_errors(ws, ncols)
    out = [hdr]
    n_data = 0
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 2:                      # 跳过双行表头
            continue
        if row_is_empty(row, ncols):   # 跳过全空行（含尾部空行）
            continue
        rec = [clean(row[j]) if j < len(row) else "" for j in range(ncols)]
        out.append(rec)
        n_data += 1
    return out, errs, n_data

wb = openpyxl.load_workbook(SRC, data_only=True)

# 履约数据
comp, comp_errs, comp_n = convert('履约类数据看板', 18, COMPLIANCE_HDR)

# ---------- 自检驳回/自检罚款：按「子项检核明细」重算，保证表格与弹窗同源 ----------
SELF_CNT, SELF_FINE = 6, 7   # 自检驳回 / 自检罚款 列下标

def aggregate_self_inspection(wb):
    """站长 + 最终检核结果=驳回 → {站点名称: [次数, 罚款, 城市]}"""
    sheet = next(s for s in wb.sheetnames if '子项检核明细' in s)
    agg = {}
    for row in wb[sheet].iter_rows(values_only=True):
        if not row or len(row) < 25:
            continue
        st, role, res = row[7], row[10], row[12]
        if st is None or role is None or res is None:
            continue
        if str(role).strip() == '站长' and str(res).strip() == '驳回':
            fine = row[24] if isinstance(row[24], (int, float)) else 0
            a = agg.setdefault(str(st).strip(), [0, 0, ''])
            a[0] += 1
            a[1] += int(fine) if float(fine).is_integer() else fine
            a[2] = str(row[4] or '').strip()
    return agg

def _is_station_name(name):
    return '站' in name or name.startswith('兴必达')

def recompute_self_cols(comp, agg):
    """站点行取明细聚合；明细里有而汇总表缺的站点行自动插入；城市/分区/公司合计逐级求和。"""
    data = comp[1:]
    rows = []                      # [level, name, row_ref]
    prev_area = prev_part = ''
    for i, r in enumerate(data):
        name = str(r[2] or '').strip()
        if r[0]: prev_area = str(r[0]).strip()
        if r[1]: prev_part = str(r[1]).strip()
        if i == 0 or '合计' in name or '网络科技' in name:
            level = 'total'
        elif _is_station_name(name):
            level = 'station'
        elif prev_part and name == prev_part:
            level = 'area'
        else:
            level = 'city'
        rows.append([level, name, r])
    # 1) 站点行按明细重算
    present = set()
    for level, name, r in rows:
        if level == 'station':
            a = agg.get(name)
            r[SELF_CNT] = a[0] if a else 0
            r[SELF_FINE] = a[1] if a else 0
            if a:
                present.add(name)
    # 2) 汇总表缺失的站点行：插入到所属城市块最后一个站点行之后
    for name, a in agg.items():
        if name in present:
            continue
        ci = next((k for k, (lv, nm, _) in enumerate(rows) if lv == 'city' and nm == a[2]), None)
        if ci is None:
            print('  !! 明细站点在汇总表找不到城市块，跳过插入:', name, '->', a[2])
            continue
        pos = ci + 1
        while pos < len(rows) and rows[pos][0] == 'station':
            pos += 1
        newrow = ['', '', name, 0, 0, 0, a[0], a[1], 0, 0, 1, 0, 0, 0, 0, 0, '-', '-']
        comp.insert(1 + pos, newrow)
        rows.insert(pos, ['station', name, newrow])
        print('  + 汇总表缺站点行，已按明细插入:', name, a[0], '次 /', a[1], '元 (', a[2], ')')
    # 3) 城市/分区/公司合计逐级求和（只动自检两列，其余列保持 Excel 原值）
    city_sum, area_sum, total = {}, {}, [0, 0]
    cur_city = cur_area = None
    for level, name, r in rows:
        if level == 'total':
            cur_city = cur_area = None
        elif level == 'area':
            cur_area, cur_city = name, None
        elif level == 'city':
            cur_city = name
        elif level == 'station':
            c, f = r[SELF_CNT] or 0, r[SELF_FINE] or 0
            total[0] += c; total[1] += f
            if cur_city:
                s = city_sum.setdefault(cur_city, [0, 0]); s[0] += c; s[1] += f
            if cur_area:
                s = area_sum.setdefault(cur_area, [0, 0]); s[0] += c; s[1] += f
    for level, name, r in rows:
        if level == 'city' and name in city_sum:
            r[SELF_CNT], r[SELF_FINE] = city_sum[name]
        elif level == 'area' and name in area_sum:
            r[SELF_CNT], r[SELF_FINE] = area_sum[name]
        elif level == 'total':
            r[SELF_CNT], r[SELF_FINE] = total
    return agg

_agg = aggregate_self_inspection(wb)
print('=== 自检明细聚合(站长+驳回) ===')
for k, v in _agg.items():
    print('  ', k, v[0], '次 /', v[1], '元')
recompute_self_cols(comp, _agg)

# 安全事故（取前14列）
acc, acc_errs, acc_n = convert('安全事故看板', 14, ACCIDENT_HDR)

# 写文件
with open(os.path.join(OUT, 'compliance.json'), 'w', encoding='utf-8') as f:
    json.dump(comp, f, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUT, 'accident.json'), 'w', encoding='utf-8') as f:
    json.dump(acc, f, ensure_ascii=False, separators=(',', ':'))

print("=== 履约数据 compliance.json ===")
print(" 数据行数:", comp_n, "| 表头列数:", len(comp[0]), "| 保留列错误值:", comp_errs if comp_errs else "无")
print(" 首条(公司):", comp[1][:4], "... 末条区域/装备合规率/健康证:", comp[1][2], comp[1][16], comp[1][17])
print("=== 安全事故 accident.json ===")
print(" 数据行数:", acc_n, "| 表头列数:", len(acc[0]), "| 保留列错误值:", acc_errs if acc_errs else "无")
print(" 首条(公司):", acc[1][:4], "... 上周完成单量/百万单事故数:", acc[1][11], acc[1][12])
print("\n样例-履约前6行区域名:", [r[2] for r in comp[1:7]])
print("样例-事故前6行区域名:", [r[2] for r in acc[1:7]])
