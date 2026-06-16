#!/usr/bin/env python3
"""
档口招商周报 — 纯 HTTP 版（无 lark-cli 依赖）
适用于：GitHub Actions / 任意 Python 3.8+ 环境

环境变量（必须）:
  FEISHU_APP_ID       - 飞书应用 App ID
  FEISHU_APP_SECRET   - 飞书应用 App Secret
  FEISHU_CHAT_ID      - 推送群 chat_id（默认 oc_214e828c8acf75a362ca87df4e96eb2e）
  FEISHU_FIELD_PROJECT - （可选）项目名称字段名，默认自动探测
  FEISHU_FIELD_SNUM    - （可选）班组编号字段名，默认自动探测
  FEISHU_FIELD_STATUS  - （可选）营业状态字段名，默认自动探测

依赖: pip install requests
"""

import os, json, sys, time, io
from datetime import datetime

try:
    import requests
except ImportError:
    print("请先安装依赖: pip install requests")
    sys.exit(1)

# ========== 配置 ==========
APP_ID = os.environ['FEISHU_APP_ID']
APP_SECRET = os.environ['FEISHU_APP_SECRET']
CHAT_ID = os.environ.get('FEISHU_CHAT_ID', 'oc_214e828c8acf75a362ca87df4e96eb2e')

BASE_TOKEN = 'CWRUbNJLZa5BmSsuWx1cvcoFnsd'
TABLE_SNUM = 'tblLiIxSybeE9AfV'
TABLE_ARCHIVE = 'tblBBBfEpOKGPSkA'
TABLE_SUMMARY = 'tblwUyMTgGVONSSv'  # 「汇总」每周看板（新增）
CHART_FIELD_ID = 'fldxPLOcoS'

API_BASE = 'https://open.feishu.cn/open-apis'

# ========== 工具函数 ==========
import traceback

def _log(msg, prefix="[INFO]"):
    print(f"{prefix} {msg}", flush=True)

def _dump_resp(resp, label="响应"):
    """打印完整响应信息用于调试"""
    _log(f"{label} HTTP {resp.status_code}")
    _log(f"Content-Type: {resp.headers.get('Content-Type', '-')}")
    _log(f"Content-Length: {resp.headers.get('Content-Length', '-')}")
    body_text = resp.text[:2000] if resp.text else "(空)"
    _log(f"{label} 内容: {body_text}")

def api_call(method, path, token=None, json_data=None, files=None, data=None, params=None):
    """通用飞书 OpenAPI 调用（增强错误日志）"""
    url = API_BASE + path
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    _log(f"请求 {method} {path}")

    try:
        if files is not None:
            resp = requests.request(
                method, url,
                data=data, files=files,
                params=params, headers=headers, timeout=30,
                proxies={'http': None, 'https': None}
            )
        elif json_data is not None:
            headers['Content-Type'] = 'application/json; charset=utf-8'
            resp = requests.request(
                method, url,
                json=json_data,
                params=params, headers=headers, timeout=30,
                proxies={'http': None, 'https': None}
            )
        else:
            resp = requests.request(
                method, url,
                params=params, headers=headers, timeout=30,
                proxies={'http': None, 'https': None}
            )
    except requests.exceptions.ConnectionError as e:
        _log(f"网络连接失败: {e}", "[ERROR]")
        _log(f"目标 URL: {url}", "[ERROR]")
        raise
    except requests.exceptions.Timeout:
        _log(f"请求超时: {url}", "[ERROR]")
        raise

    # 检查 HTTP 状态码
    if resp.status_code != 200:
        _log(f"HTTP 错误 {resp.status_code}", "[ERROR]")
        _dump_resp(resp, "错误响应")
        raise RuntimeError(f"飞书 API 返回 HTTP {resp.status_code}: {resp.text[:500]}")

    # 尝试解析 JSON
    try:
        body = resp.json()
    except Exception:
        _log(f"JSON 解析失败", "[ERROR]")
        _dump_resp(resp, "非JSON响应")
        raise

    # 检查飞书业务错误码
    code = body.get('code', -1)
    if code != 0:
        _log(f"飞书错误 code={code} msg={body.get('msg')} request_id={body.get('request_id','-')}", "[ERROR]")
        _log(f"完整响应: {json.dumps(body, ensure_ascii=False)[:1000]}", "[ERROR]")
        raise RuntimeError(f"飞书 API 错误 [{code}]: {body.get('msg')}")

    return body.get('data', body)


def get_tenant_token():
    _log("获取 tenant_access_token...")
    data = api_call('POST', '/auth/v3/tenant_access_token/internal',
                    json_data={'app_id': APP_ID, 'app_secret': APP_SECRET})
    token = data['tenant_access_token']
    _log(f"成功（有效期 {data['expire']}s）")
    return token


# ========== Step 1: 拉取班组数据 ==========
def fetch_records(token):
    print('\n[Step 1] 拉取班组表数据...')
    all_records = []
    page_token = None
    while True:
        params = {'page_size': 500}
        if page_token:
            params['page_token'] = page_token
        data = api_call('GET', f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_SNUM}/records',
                        token, params=params)
        items = data.get('items', [])
        all_records.extend(items)
        if not data.get('has_more'):
            break
        page_token = data.get('page_token')
        time.sleep(0.3)
    print(f"  共 {len(all_records)} 条记录")
    return all_records


# ========== Step 2: 探测字段名 + 解析统计 ==========
def detect_field_names(sample_fields):
    """自动探测字段名（精确匹配）"""
    result = {}
    for fname in sample_fields:
        if fname == '项目名称':
            result['project'] = fname
        if fname == '班组编号':
            result['snum'] = fname
        if fname == '营业状态':
            result['status'] = fname
    return result


def parse_field_value(fields, field_name):
    """从 fields dict 中取值，兼容标量/list"""
    val = fields.get(field_name)
    if val is None:
        return ''
    if isinstance(val, list):
        return str(val[0]).strip() if val else ''
    return str(val).strip()


def parse_and_stats(records):
    print('\n[Step 2] 解析数据并统计...')

    if not records:
        raise RuntimeError('未拉取到任何记录，请检查 Base Token 和表 ID')

    # 探测字段名
    sample_fields = records[0].get('fields', {})
    field_map = detect_field_names(sample_fields)

    # 允许环境变量覆盖
    for key, env_key in [('project', 'FEISHU_FIELD_PROJECT'),
                          ('snum', 'FEISHU_FIELD_SNUM'),
                          ('status', 'FEISHU_FIELD_STATUS')]:
        env_val = os.environ.get(env_key)
        if env_val:
            field_map[key] = env_val
            print(f"  使用环境变量字段名 {key}={env_val}")

    print(f"  字段映射: {field_map}")

    if 'project' not in field_map or 'snum' not in field_map:
        print("  错误：无法自动识别字段名，请设置环境变量：")
        print("  FEISHU_FIELD_PROJECT, FEISHU_FIELD_SNUM, FEISHU_FIELD_STATUS")
        raise RuntimeError("字段名无法识别，请在 GitHub Secrets 中设置环境变量")

    raw = []
    for rec in records:
        f = rec.get('fields', {})
        pname = parse_field_value(f, field_map['project'])
        snum = parse_field_value(f, field_map['snum'])
        status = parse_field_value(f, field_map.get('status', ''))
        if pname and snum:
            raw.append((pname, snum, status))

    print(f"  有效记录: {len(raw)} 条")

    projects = {}
    for pname, snum, status in raw:
        if pname not in projects:
            projects[pname] = {'ops': 0, 'vacs': 0, 'vac_nums': []}
        if status == '营业中':
            projects[pname]['ops'] += 1
        elif status == '待招商':
            projects[pname]['vacs'] += 1
            projects[pname]['vac_nums'].append(snum)

    # 只保留有待招商的项目
    vac_projects = {k: v for k, v in projects.items() if v['vacs'] > 0}
    total_vacs = sum(v['vacs'] for v in vac_projects.values())
    total_all = sum(v['ops'] + v['vacs'] for v in vac_projects.values())
    vac_rate = total_vacs / total_all * 100 if total_all else 0

    print(f"  有待招商项目: {len(vac_projects)} 个")
    print(f"  待招商档口数: {total_vacs}")
    print(f"  空置率: {vac_rate:.2f}%")
    return projects, vac_projects, total_vacs, total_all, vac_rate


# ========== Step 3: 生成柱形图 ==========
def generate_chart(vac_projects):
    print('\n[Step 3] 生成柱形图...')
    import urllib.parse
    sorted_items = sorted(vac_projects.items(), key=lambda x: x[1]['vacs'], reverse=True)
    chart_config = {
        'type': 'horizontalBar',
        'data': {
            'labels': [k for k, v in sorted_items],
            'datasets': [
                {'label': '营业中', 'data': [v['ops'] for k, v in sorted_items], 'backgroundColor': '#378ADD'},
                {'label': '待招商', 'data': [v['vacs'] for k, v in sorted_items], 'backgroundColor': '#EF9F27'}
            ]
        },
        'options': {
            'scales': {
                'xAxes': [{'stacked': True, 'ticks': {'stepSize': 5}}],
                'yAxes': [{'stacked': True}]
            },
            'legend': {'position': 'bottom', 'labels': {'fontSize': 13, 'padding': 16, 'usePointStyle': True}}
        }
    }
    chart_json = json.dumps(chart_config, separators=(',', ':'))
    url = 'https://quickchart.io/chart?w=600&h=350&c=' + urllib.parse.quote(chart_json)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    png_bytes = resp.content
    print(f"  图表大小: {len(png_bytes)//1024} KB")
    return png_bytes


# ========== Step 4: 上传图片到飞书 IM ==========
def upload_image(token, png_bytes):
    print('\n[Step 4] 上传图片到飞书 IM...')
    files = {
        'image': ('chart.png', io.BytesIO(png_bytes), 'image/png')
    }
    data = {'image_type': 'message'}
    result = api_call('POST', '/im/v1/images', token, data=data, files=files)
    image_key = result.get('image_key', '')
    print(f"  image_key: {image_key}")
    return image_key


# ========== Step 5: 构建明细文本 ==========
def build_detail_text(projects, vac_projects):
    def snum_key(s):
        try: return int(s)
        except: return 9999

    vac_list = sorted(vac_projects.items(), key=lambda x: x[1]['vacs'], reverse=True)
    lines = []
    for i, (pname, pdata) in enumerate(vac_list):
        vac_nums = sorted(pdata['vac_nums'], key=snum_key)
        f1 = [s for s in vac_nums if 0 < int(s) < 200]
        f2 = [s for s in vac_nums if 200 <= int(s) < 300]
        f3 = [s for s in vac_nums if int(s) >= 300]
        t = pdata['ops'] + pdata['vacs']
        r = pdata['vacs'] / t * 100 if t else 0
        if i > 0:
            lines.append('')
        lines.append(f"「{pname}」-共{t}个档口，待招商{pdata['vacs']}个（空置率：{r:.2f}%）")
        if f1:
            lines.append(f"1F：{', '.join(f1)}")
        if f2:
            lines.append(f"2F：{', '.join(f2)}")
        if f3:
            lines.append(f"3F：{', '.join(f3)}")
    return '\n'.join(lines)


# ========== Step 6: 发送卡片 ==========
def send_card(token, image_key, total_vacs, vac_rate, vac_projects_count, detail_text):
    print('\n[Step 6] 发送卡片到群...')
    today = datetime.now().strftime('%Y.%m.%d')
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 档口状态周报 · {today}"},
            "template": "blue"
        },
        "elements": [
            {"tag": "img", "img_key": image_key,
             "alt": {"tag": "plain_text", "content": "各项目档口状态堆叠柱形图"},
             "mode": "fit_horizontal", "preview": True},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content":
                f"待招商项目 **{vac_projects_count}** 个　待招商数量 **{total_vacs}** 　空置率 **{vac_rate:.2f}%**"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": detail_text}},
            {"tag": "hr"},
            {"tag": "note", "elements": [
                {"tag": "plain_text", "content": "数据来源：综合运营管理 Base · 每周五 17:00 自动推送"}]}
        ]
    }
    payload = {
        'receive_id': CHAT_ID,
        'msg_type': 'interactive',
        'content': json.dumps(card, ensure_ascii=False)
    }
    result = api_call('POST', '/im/v1/messages?receive_id_type=chat_id', token, json_data=payload)
    msg_id = result.get('message_id', '')
    print(f"  消息已发送: {msg_id}")
    return msg_id


# ========== Step 7: 归档到多维表格（含附件上传） ==========
def archive_record(token, total_vacs, vac_rate, vac_projects_count, detail_text, png_bytes):
    print('\n[Step 7] 归档到多维表格...')
    today = datetime.now().strftime('%Y.%m.%d')
    title = f"档口招商周报{today}"
    # 飞书日期时间类型：传毫秒级时间戳
    push_ts = int(time.time() * 1000)

    # 先上传素材获取 file_token
    print('  [Step 7.1] 上传图表素材...')
    files = {
        'file': ('chart.png', io.BytesIO(png_bytes), 'image/png')
    }
    data = {
        'file_name': 'chart.png',
        'parent_type': 'bitable',
        'parent_node': BASE_TOKEN,
        'size': str(len(png_bytes))
    }
    upload_result = api_call('POST', '/drive/v1/medias/upload_all', token, data=data, files=files)
    file_token = upload_result.get('file_token', '')
    print(f"  file_token: {file_token}")

    # 1. 归档到「档口」分析看板（保留原有逻辑）
    records_data = [{
        'fields': {
            '标题': title,
            '推送日期': push_ts,
            '待招商': total_vacs,
            '空置率(%)': round(vac_rate / 100, 4),   # 小数 → 飞书百分比字段
            '待招商项目数': vac_projects_count,
            '招商情况': detail_text,
            '柱形图': [{'file_token': file_token}] if file_token else []
        }
    }]
    result = api_call('POST',
                       f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ARCHIVE}/records/batch_create',
                       token, json_data={'records': records_data})
    record_id = result.get('records', [{}])[0].get('record_id', '')
    print(f"  「档口」分析看板归档记录已创建: {record_id}")

    # 2. 归档到「汇总」每周看板（新增）
    print('  [Step 7.2] 归档到「汇总」每周看板...')
    # 生成 HTML 页面预览链接（GitHub Pages）
    html_filename = f"{today.replace('.', '-')}-merchant.html"
    page_preview_url = f"https://zchenwenxuan-design.github.io/veg-aggregate/reports/{html_filename}"

    summary_records_data = [{
        'fields': {
            '标题': title,
            '推送日期': push_ts,
            '类型': '招商',
            '推送内容': detail_text,
            '页面预览': page_preview_url,
        }
    }]

    result2 = api_call('POST',
                        f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_SUMMARY}/records/batch_create',
                        token, json_data={'records': summary_records_data})
    summary_record_id = result2.get('records', [{}])[0].get('record_id', '')
    print(f"  「汇总」每周看板归档记录已创建: {summary_record_id}")

    return record_id


# ========== 主流程 ==========
def main():
    print('=== 档口招商周报（纯 HTTP 版）===\n')
    token = get_tenant_token()

    records = fetch_records(token)
    projects, vac_projects, total_vacs, total_all, vac_rate = parse_and_stats(records)
    vac_projects_count = len(vac_projects)

    png_bytes = generate_chart(vac_projects)
    image_key = upload_image(token, png_bytes)
    detail_text = build_detail_text(projects, vac_projects)
    send_card(token, image_key, total_vacs, vac_rate, vac_projects_count, detail_text)
    record_id = archive_record(token, total_vacs, vac_rate, vac_projects_count, detail_text, png_bytes)

    print('\n=== 全部完成 ===\n')


if __name__ == '__main__':
    for key in ['FEISHU_APP_ID', 'FEISHU_APP_SECRET']:
        if key not in os.environ:
            print(f"错误：环境变量 {key} 未设置")
            sys.exit(1)
    main()
