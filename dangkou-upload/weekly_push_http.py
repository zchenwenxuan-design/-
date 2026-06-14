#!/usr/bin/env python3
"""
档口招商周报 — 纯 HTTP 版（无 lark-cli 依赖）
适用于：GitHub Actions / 任意 Python 3.8+ 环境

环境变量（必须）:
  FEISHU_APP_ID       - 飞书应用 App ID
  FEISHU_APP_SECRET   - 飞书应用 App Secret
  FEISHU_CHAT_ID      - 推送群 chat_id（默认 oc_214e828c8acf75a362ca87df4e96eb2e）

依赖: pip install requests
"""

import os, json, sys, time, io, traceback
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
CHART_FIELD_ID = 'fldxPLOcoS'

API_BASE = 'https://open.feishu.cn/open-apis'

# ========== 工具函数 ==========
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
                proxies={'http': None, 'https': None}, trust_env=False
            )
        elif json_data is not None:
            headers['Content-Type'] = 'application/json; charset=utf-8'
            resp = requests.request(
                method, url,
                json=json_data,
                params=params, headers=headers, timeout=30,
                proxies={'http': None, 'https': None}, trust_env=False
            )
        else:
            resp = requests.request(
                method, url,
                params=params, headers=headers, timeout=30,
                proxies={'http': None, 'https': None}, trust_env=False
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
    _log("拉取班组表数据...")
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
    _log(f"共 {len(all_records)} 条记录")
    return all_records


# ========== Step 2: 解析统计 ==========
def parse_and_stats(records):
    """从记录列表解析项目、班组编号、状态，按项目分组统计"""
    projects = {}
    for rec in records:
        fields = rec.get('fields', {})
        # 自动探测字段名（支持模糊匹配）
        pname = None
        snum = None
        status = None
        for k, v in fields.items():
            v_str = str(v).strip() if v else ''
            if '项目' in k and not pname:
                pname = v_str
            elif ('班组' in k or '编号' in k or '档口' in k) and not snum:
                snum = v_str
            elif ('状态' in k or '营业' in k) and not status:
                status = v_str
        if not pname or not snum:
            continue
        if pname not in projects:
            projects[pname] = {'ops': 0, 'vacs': 0, 'vac_nums': []}
        if status in ('待招商', '招商中', '空置'):
            projects[pname]['vacs'] += 1
            projects[pname]['vac_nums'].append(snum)
        elif status in ('营业中', '已出租', '在租'):
            projects[pname]['ops'] += 1
    return projects


# ========== Step 3: 生成柱形图 ==========
def gen_chart(vac_projects):
    _log("生成柱形图...")
    labels = [p[0] for p in vac_projects]
    ops_data = [p[1]['ops'] for p in vac_projects]
    vac_data = [p[1]['vacs'] for p in vac_projects]

    chart_config = {
        "type": "horizontalBar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "营业中", "data": ops_data, "backgroundColor": "#5B8FF9"},
                {"label": "待招商", "data": vac_data, "backgroundColor": "#F46649"}
            ]
        },
        "options": {
            "scales": {
                "xAxes": [{"stacked": True, "ticks": {"beginAtZero": True}}],
                "yAxes": [{"stacked": True}]
            },
            "plugins": {"datalabels": {"display": False}}
        }
    }
    chart_url = f"https://quickchart.io/chart?c={json.dumps(chart_config)}"
    resp = requests.get(chart_url, timeout=30)
    with open('chart_tmp.png', 'wb') as f:
        f.write(resp.content)
    _log("柱形图保存成功")


# ========== Step 4: 上传图片 ==========
def upload_image(token):
    _log("上传柱形图...")
    with open('chart_tmp.png', 'rb') as f:
        img_data = f.read()
    data = {'image_type': 'message'}
    files = {'image': ('chart.png', img_data, 'image/png')}
    result = api_call('POST', '/im/v1/images', token, data=data, files=files)
    image_key = result['image_key']
    _log(f"image_key: {image_key}")
    return image_key


# ========== Step 5: 生成推送内容 ==========
def build_detail_text(vac_projects):
    lines = []
    def snum_key(s):
        try: return int(s)
        except: return 9999
    for i, (pname, pdata) in enumerate(vac_projects):
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
    _log("发送卡片到群...")
    today = datetime.now().strftime('%Y.%m.%d')
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📊 档口状态周报 · {today}"},
            "template": "blue"
        },
        "elements": [
            {"tag": "img", "img_key": image_key, "alt": {"tag": "plain_text", "content": "待招商档口统计"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**汇总**：**{vac_projects_count}** 个项目有待招商档口，共 **{total_vacs}** 个待招商（空置率 **{vac_rate:.2f}%**）"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": detail_text.replace('\n', '  \n')}}
        ]
    }
    payload = {
        "receive_id": CHAT_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False)
    }
    api_call('POST', '/im/v1/messages?receive_id_type=chat_id', token, json_data=payload)
    _log("卡片发送成功！")


# ========== Step 7: 归档到多维表格 ==========
def archive_record(token, total_vacs, vac_rate, vac_projects_count, detail_text, image_key):
    _log("归档到「档口」招商周报表...")
    now = datetime.now()
    title = f"档口招商周报{now.strftime('%Y.%m.%d')}"
    push_date = now.strftime('%Y-%m-%d %H:%M')

    fields = {
        "标题": title,
        "推送日期": push_date,
        "待招商": total_vacs,
        "空置率(%)": vac_rate / 100,  # 小数形式（飞书百分比字段→显示%）
        "待招商项目数": vac_projects_count,
        "招商情况": detail_text
    }

    result = api_call('POST',
                      f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ARCHIVE}/records/batch_create',
                      token,
                      json_data={"records": [{"fields": fields}]})
    records_list = result.get('records', [])
    if not records_list:
        raise RuntimeError("归档写入失败：无返回记录")
    record_id = records_list[0].get('record_id')
    _log(f"记录已创建: {record_id}")

    # 上传柱形图附件
    _log("上传柱形图附件...")
    with open('chart_tmp.png', 'rb') as f:
        img_bytes = f.read()
    # 附件上传需两步：1)上传文件 2)绑定到字段
    up_result = api_call('POST',
                         f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ARCHIVE}/records/{record_id}/attachments',
                         token,
                         files={'file': ('chart.png', img_bytes, 'image/png')},
                         data={'field_id': CHART_FIELD_ID})
    _log("附件上传成功")
    return record_id


# ========== 主流程 ==========
def main():
    _log("===== 档口招商周报 =====", "[START]")

    token = get_tenant_token()

    records = fetch_records(token)

    projects = parse_and_stats(records)
    vac_projects = [(k, v) for k, v in projects.items() if v['vacs'] > 0]
    vac_projects.sort(key=lambda x: x[1]['vacs'], reverse=True)

    total_all = sum(v['ops'] + v['vacs'] for _, v in vac_projects)
    total_vacs = sum(v['vacs'] for _, v in vac_projects)
    vac_rate = total_vacs / total_all * 100 if total_all else 0
    vac_projects_count = len(vac_projects)

    _log(f"统计: {vac_projects_count}个项目, {total_vacs}/{total_all}待招商, 空置率{vac_rate:.2f}%")

    gen_chart(vac_projects)
    image_key = upload_image(token)
    detail_text = build_detail_text(vac_projects)

    send_card(token, image_key, total_vacs, vac_rate, vac_projects_count, detail_text)
    archive_record(token, total_vacs, vac_rate, vac_projects_count, detail_text, image_key)

    # 清理
    if os.path.exists('chart_tmp.png'):
        os.remove('chart_tmp.png')

    _log("===== 完成 =====", "[DONE]")


if __name__ == '__main__':
    main()
