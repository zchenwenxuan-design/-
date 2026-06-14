"""
每周五档口周报数据生成器 (纯数据处理，不调lark-cli)
输入: data/raw_data.json (已由Bash预拉取)
输出: chart_tmp.png, data/cards/card1_overview.json, data/cards/card2_detail.json, data/summary.json
"""
import json, os, sys
import urllib.request, urllib.parse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, 'data', 'raw_data.json')
CHART_PATH = os.path.join(BASE, 'chart_tmp.png')
CARDS_DIR = os.path.join(BASE, 'data', 'cards')
SUMMARY_PATH = os.path.join(BASE, 'data', 'summary.json')
TODAY = datetime.now().strftime('%Y.%m.%d')

# ====== Step 1: 读取数据 ======
with open(DATA_PATH, encoding='utf-8') as f:
    raw = json.load(f)

# 解析 lark-cli response → data.data → 提取 index19=项目, index14=班组, index9=状态
raw_records = raw.get('data', raw).get('data', raw.get('data', raw))
records = []
for r in raw_records:
    if not isinstance(r, list) or len(r) < 20:
        continue
    pname = str(r[19][0]).strip() if isinstance(r[19], list) and r[19] else ''
    snum = str(r[14][0]).strip() if isinstance(r[14], list) and r[14] else ''
    status = str(r[9][0]).strip() if isinstance(r[9], list) and r[9] else ''
    if pname and snum:
        records.append((pname, snum, status))

print(f"  共 {len(records)} 条记录")

# ====== Step 2: 分组统计 ======
projects = {}
for pname, snum, status in records:
    if not pname or not snum:
        continue
    if pname not in projects:
        projects[pname] = {'ops': 0, 'vacs': 0}
    if status == '营业中':
        projects[pname]['ops'] += 1
    elif status == '待招商':
        projects[pname]['vacs'] += 1

# 按待招商占比降序
items = sorted(
    projects.items(),
    key=lambda x: x[1]['vacs']/(x[1]['ops']+x[1]['vacs']) if (x[1]['ops']+x[1]['vacs'])>0 else 0,
    reverse=True
)

total_ops = sum(v['ops'] for _, v in items)
total_vacs = sum(v['vacs'] for _, v in items)
total_all = total_ops + total_vacs
overall_rate = total_ops / total_all * 100 if total_all else 100
full_projects = sum(1 for _, v in items if v['vacs'] == 0)
vac_projects = sum(1 for _, v in items if v['vacs'] > 0)

summary = {
    'date': TODAY,
    'total_ops': total_ops,
    'total_vacs': total_vacs,
    'total_all': total_all,
    'overall_rate': round(overall_rate, 1),
    'full_projects': full_projects,
    'total_projects': len(items),
    'vac_projects': vac_projects
}

os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False)

print(f"  营业中: {total_ops} | 待招商: {total_vacs} | 总计: {total_all}")
print(f"  招商率: {overall_rate:.1f}% | 已满: {full_projects}/{len(items)}")

# ====== Step 3: 生成柱形图（只显示有待招商的项目） ======
vac_chart_items = [(k, v) for k, v in items if v['vacs'] > 0]
chart_config = {
    'type': 'horizontalBar',
    'data': {
        'labels': [k for k, v in vac_chart_items],
        'datasets': [
            {'label': '营业中', 'data': [v['ops'] for k, v in vac_chart_items], 'backgroundColor': '#378ADD'},
            {'label': '待招商', 'data': [v['vacs'] for k, v in vac_chart_items], 'backgroundColor': '#EF9F27'}
        ]
    },
    'options': {
        'scales': {
            'xAxes': [{'stacked': True, 'ticks': {'stepSize': 5}}],
            'yAxes': [{'stacked': True}]
        },
        'legend': {
            'position': 'bottom',
            'labels': {'fontSize': 13, 'padding': 16, 'usePointStyle': True}
        },
        'plugins': {
            'datalabels': {
                'display': True,
                'color': '#fff',
                'font': {'weight': 'bold', 'size': 12}
            }
        }
    }
}

chart_json = json.dumps(chart_config, separators=(',', ':'))
chart_url = 'https://quickchart.io/chart?w=600&h=350&c=' + urllib.parse.quote(chart_json)
resp = urllib.request.urlopen(chart_url)
with open(CHART_PATH, 'wb') as f:
    f.write(resp.read())
print(f"  图表已保存: chart_tmp.png")

# ====== Step 4: 生成合并卡片 JSON ======
vac_rate = total_vacs / total_all * 100 if total_all else 0

# 按待招商数量降序排列明细
vac_projects_list = sorted(
    [(k, v) for k, v in items if v['vacs'] > 0],
    key=lambda x: x[1]['vacs'], reverse=True
)

def snum_key(s):
    try: return int(s)
    except: return 9999

# 构建明细文本（div格式，避免表格截断）
detail_lines = []
for i, (pname, pdata) in enumerate(vac_projects_list):
    vac_nums = sorted(
        [snum for p, snum, s in records if p == pname and s == '待招商'],
        key=snum_key
    )
    f1 = [s for s in vac_nums if 0 < int(s) < 200]
    f2 = [s for s in vac_nums if 200 <= int(s) < 300]
    f3 = [s for s in vac_nums if int(s) >= 300]
    t = pdata['ops'] + pdata['vacs']
    r = pdata['vacs'] / t * 100 if t else 0

    if i > 0:
        detail_lines.append('')
    detail_lines.append(f"「{pname}」-共{t}个档口，待招商{pdata['vacs']}个（空置率：{r:.2f}%）")
    if f1:
        detail_lines.append(f"1F：{', '.join(f1)}")
    if f2:
        detail_lines.append(f"2F：{', '.join(f2)}")
    if f3:
        detail_lines.append(f"3F：{', '.join(f3)}")

merged_card = {
    "config": {"wide_screen_mode": True},
    "header": {
        "title": {"tag": "plain_text", "content": f"📊 档口状态周报 · {TODAY}"},
        "template": "blue"
    },
    "elements": [
        # 1) 柱形图
        {
            "tag": "img",
            "img_key": "IMG_KEY_PLACEHOLDER",
            "alt": {"tag": "plain_text", "content": "各项目档口状态堆叠柱形图"},
            "mode": "fit_horizontal",
            "preview": True
        },
        {"tag": "hr"},
        # 2) 汇总：待招商项目数、待招商数量、空置率
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"待招商项目 **{len(vac_projects_list)}** 个　"
                    f"待招商数量 **{total_vacs}** 　"
                    f"空置率 **{vac_rate:.2f}%**"
                )
            }
        },
        {"tag": "hr"},
        # 3) 明细（div格式，不截断）
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(detail_lines)
            }
        },
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": "数据来源：综合运营管理 Base · 每周五 18:00 自动推送"}
            ]
        }
    ]
}

os.makedirs(CARDS_DIR, exist_ok=True)
with open(os.path.join(CARDS_DIR, 'weekly_merged.json'), 'w', encoding='utf-8') as f:
    json.dump(merged_card, f, ensure_ascii=False, indent=2)

msg_file = os.path.join(CARDS_DIR, 'weekly_msg.txt')
with open(msg_file, 'w', encoding='utf-8') as f:
    json.dump(merged_card, f, ensure_ascii=False)

print(f"  合并卡片已生成: data/cards/weekly_merged.json")
print(f"  (单卡片发送文本: data/cards/weekly_msg.txt)")
print(f"  SUMMARY: {json.dumps(summary, ensure_ascii=False)}")

# ====== Step 5: 归档信息 ======
archive_info = {
    "table_id": "tblBBBfEpOKGPSkA",
    "base_token": "CWRUbNJLZa5BmSsuWx1cvcoFnsd",
    "chart_field_id": "fldxPLOcoS",
    "timestamp_ms": int(__import__('time').time() * 1000),
    "push_date": datetime.now().strftime('%Y-%m-%d %H:%M'),
    "title": f"档口招商周报{TODAY}",
    "total_vacs": total_vacs,
    "vac_rate": round(vac_rate / 100, 4),  # 小数形式（百分比字段0.3008→30.08%）
    "vac_projects_count": len(vac_projects_list),
    "detail_text": "\n".join(detail_lines)
}
archive_path = os.path.join(BASE, 'data', 'archive_info.json')
with open(archive_path, 'w', encoding='utf-8') as f:
    json.dump(archive_info, f, ensure_ascii=False)
print(f"  归档参数已写出: data/archive_info.json")
print(f"  Done.")
