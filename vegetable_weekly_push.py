#!/usr/bin/env python3
"""
青菜价格异常预警周报 — 纯 HTTP 版
适用于：GitHub Actions / 任意 Python 3.8+ 环境

环境变量（必须）:
  FEISHU_APP_ID       - 飞书应用 App ID
  FEISHU_APP_SECRET   - 飞书应用 App Secret
  FEISHU_CHAT_ID      - 推送群 chat_id（默认 oc_214e828c8acf75a362ca87df4e96eb2e）

依赖: pip install requests
"""

import os, json, sys, time, io
from datetime import datetime, timedelta

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
TABLE_DETAIL = 'tbl4aO9rKwKxlXzR'  # 「青菜」填报明细
TABLE_ARCHIVE = 'tbl1ShD40AB0BeC0'  # 「青菜」分析看板
TABLE_SUPPLIER = 'tblgGb0oFtei8uAx'  # 供应商表

API_BASE = 'https://open.feishu.cn/open-apis'

# 预警阈值
ALERT_THRESHOLD = 0.15  # 15%

# 项目类型配置（周末是否营业）
PROJECT_WEEKEND_OPEN = {
    '嘉应学院': True,      # 大学，周末营业
    '天河交通': True,      # 大专，周末营业
    '花都工商': False,     # 初高中，周末休息
    '清远建设': False,     # 初高中，周末休息
    '清远交通': True,      # 大专，周末营业
    '连平中学': False,     # 初高中，周末休息
    '仲恺学院': True,      # 大学，周末营业
    '海运学院': True,      # 大专，周末营业
    '天河生态': True,      # 大学，周末营业
    '天河科贸': True,      # 大专，周末营业
}

# ========== 工具函数 ==========
def _log(msg, prefix="[INFO]"):
    print(f"{prefix} {msg}", flush=True)

def api_call(method, path, token=None, json_data=None, files=None, data=None, params=None):
    """通用飞书 OpenAPI 调用"""
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
        raise
    except requests.exceptions.Timeout:
        _log(f"请求超时: {url}", "[ERROR]")
        raise

    if resp.status_code != 200:
        _log(f"HTTP 错误 {resp.status_code}: {resp.text[:500]}", "[ERROR]")
        raise RuntimeError(f"飞书 API 返回 HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        body = resp.json()
    except Exception:
        _log(f"JSON 解析失败: {resp.text[:500]}", "[ERROR]")
        raise

    code = body.get('code', -1)
    if code != 0:
        _log(f"飞书错误 code={code} msg={body.get('msg')}", "[ERROR]")
        raise RuntimeError(f"飞书 API 错误 [{code}]: {body.get('msg')}")

    return body.get('data', body)


def get_tenant_token():
    _log("获取 tenant_access_token...")
    data = api_call('POST', '/auth/v3/tenant_access_token/internal',
                    json_data={'app_id': APP_ID, 'app_secret': APP_SECRET})
    token = data['tenant_access_token']
    _log(f"成功（有效期 {data['expire']}s）")
    return token


# ========== Step 1: 拉取本周和上周数据 ==========
def fetch_records(token):
    """拉取本周和上周的青菜填报明细"""
    print('\n[Step 1] 拉取青菜数据...')
    
    # 计算日期范围
    today = datetime.now()
    this_week_start = today - timedelta(days=7)
    last_week_start = today - timedelta(days=14)
    
    this_week_records = []
    last_week_records = []
    page_token = None
    
    while True:
        params = {'page_size': 500}
        if page_token:
            params['page_token'] = page_token
        
        data = api_call('GET', f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_DETAIL}/records',
                        token, params=params)
        items = data.get('items', [])
        
        for item in items:
            fields = item.get('fields', {})
            date_val = fields.get('日期')
            if date_val:
                # 飞书日期格式: 毫秒级时间戳或 yyyy/MM/dd
                if isinstance(date_val, int):
                    record_date = datetime.fromtimestamp(date_val / 1000)
                else:
                    try:
                        record_date = datetime.strptime(str(date_val), '%Y/%m/%d')
                    except:
                        continue
                
                # 分类到本周或上周
                if this_week_start <= record_date <= today:
                    this_week_records.append(item)
                elif last_week_start <= record_date < this_week_start:
                    last_week_records.append(item)
        
        if not data.get('has_more'):
            break
        page_token = data.get('page_token')
        time.sleep(0.3)
    
    print(f"  本周共 {len(this_week_records)} 条记录")
    print(f"  上周共 {len(last_week_records)} 条记录")
    return this_week_records, last_week_records


# ========== Step 2: 解析数据并统计 ==========
def parse_and_stats(this_week_records, last_week_records, supplier_map):
    """解析青菜数据，统计单价差异和预警"""
    print('\n[Step 2] 解析数据并统计...')
    
    if not this_week_records:
        raise RuntimeError('本周未拉取到任何青菜记录')
    
    # 数据结构: {食材名称: {项目: {单价列表, 数量列表, 金额列表, 供应商集合, 日期列表}}}
    veg_data = {}
    
    for rec in this_week_records:
        f = rec.get('fields', {})
        
        # 提取字段
        veg_name = _get_field_value(f, '统一食材名称')
        project = _get_field_value(f, '项目名称')
        price = _get_field_value(f, '单价', numeric=True)
        qty = _get_field_value(f, '数量', numeric=True)
        amount = _get_field_value(f, '金额', numeric=True)
        # 供应商名称是 link 字段，返回 record_id，需要解析
        supplier_id = _get_field_value(f, '供应商名称')
        supplier = resolve_supplier_id(supplier_id, supplier_map)
        date_val = f.get('日期')
        
        if not veg_name or not project or price is None:
            continue
        
        if veg_name not in veg_data:
            veg_data[veg_name] = {}
        
        if project not in veg_data[veg_name]:
            veg_data[veg_name][project] = {
                'prices': [], 'qtys': [], 'amounts': [], 'suppliers': set(), 'dates': []
            }
        
        veg_data[veg_name][project]['prices'].append(price)
        veg_data[veg_name][project]['qtys'].append(qty or 0)
        veg_data[veg_name][project]['amounts'].append(amount or 0)
        veg_data[veg_name][project]['dates'].append(date_val)
        if supplier:
            veg_data[veg_name][project]['suppliers'].add(supplier)
    
    # 计算统计指标
    stats = _calculate_stats(veg_data)
    
    # 计算项目采购成本TOP5（含上周对比）
    project_costs = _calculate_project_costs(veg_data, this_week_records, last_week_records)
    
    # 计算数据完整度
    data_completeness = _calculate_data_completeness(this_week_records)
    
    print(f"  涉及食材: {len(stats)} 种")
    print(f"  涉及项目: {len(project_costs)} 个")
    return stats, project_costs, veg_data, data_completeness


def _get_field_value(fields, field_name, numeric=False):
    """
    从 fields 中提取字段值，兼容飞书所有字段类型：
    - text/number/select: 直接返回值（string 或 number）
    - lookup: {"type":1, "value": [{"text":"xxx", "type":"text"}]}
    - link:   {"link_record_ids": ["recXXX"]}
    - formula: 直接返回计算结果（number 或 string）
    - datetime: int（毫秒时间戳）
    """
    val = fields.get(field_name)
    if val is None:
        return None

    # lookup 字段: {"type": 1, "value": [{"text": "生菜", "type": "text"}, ...]}
    if isinstance(val, dict) and 'value' in val:
        value_list = val.get('value', [])
        if isinstance(value_list, list) and value_list:
            first = value_list[0]
            if isinstance(first, dict) and 'text' in first:
                val = first['text']
            elif isinstance(first, str):
                val = first
            else:
                val = str(first)
        else:
            return None

    # link 字段: {"link_record_ids": ["recXXX", ...]}
    if isinstance(val, dict) and 'link_record_ids' in val:
        ids = val.get('link_record_ids', [])
        return ids[0] if ids else None  # 返回 record_id，由调用方解析

    # 列表类型（多选等）
    if isinstance(val, list):
        val = val[0] if val else None

    if val is None:
        return None

    # dict 类型兜底（单选等）
    if isinstance(val, dict):
        val = val.get('text') or val.get('id', '')

    if numeric and val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    return str(val).strip() if val else None


def fetch_supplier_names(token):
    """预加载供应商表，建立 record_id -> 供应商名称 的映射"""
    print('\n[Step 1.1] 加载供应商名称映射...')
    supplier_map = {}
    page_token = None

    while True:
        params = {'page_size': 500, 'field_names': '["供应商名称"]'}
        if page_token:
            params['page_token'] = page_token

        data = api_call('GET', f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_SUPPLIER}/records',
                        token, params=params)
        items = data.get('items', [])

        for item in items:
            record_id = item.get('record_id', '')
            fields = item.get('fields', {})
            name = _get_field_value(fields, '供应商名称')
            if name:
                supplier_map[record_id] = name

        if not data.get('has_more'):
            break
        page_token = data.get('page_token')
        time.sleep(0.2)

    print(f"  已加载 {len(supplier_map)} 个供应商名称")
    return supplier_map


def resolve_supplier_id(supplier_id, supplier_map):
    """将供应商 record_id 解析为可读名称"""
    if not supplier_id:
        return None
    name = supplier_map.get(supplier_id)
    if name:
        return name
    # 如果找不到映射，返回 ID 的后6位作为标识
    return f"供应商({supplier_id[-6:]})"


def _calculate_stats(veg_data):
    """计算每种食材的跨项目统计和预警"""
    stats = []
    
    for veg_name, projects in veg_data.items():
        # 计算每个项目的均价和总量
        project_stats = []
        all_prices = []
        total_qty = 0
        total_amount = 0
        
        for project, data in projects.items():
            avg_price = sum(data['prices']) / len(data['prices']) if data['prices'] else 0
            qty = sum(data['qtys'])
            amount = sum(data['amounts'])
            suppliers = list(data['suppliers'])
            
            project_stats.append({
                'project': project,
                'avg_price': avg_price,
                'qty': qty,
                'amount': amount,
                'suppliers': suppliers,
                'price_count': len(data['prices'])
            })
            
            all_prices.extend(data['prices'])
            total_qty += qty
            total_amount += amount
        
        # 计算近7日均价（所有项目的平均）
        week_avg = sum(all_prices) / len(all_prices) if all_prices else 0
        
        # 找出最高和最低
        sorted_by_price = sorted(project_stats, key=lambda x: x['avg_price'], reverse=True)
        max_price = sorted_by_price[0] if sorted_by_price else None
        min_price = sorted_by_price[-1] if sorted_by_price else None
        
        # 计算价差
        price_diff = max_price['avg_price'] - min_price['avg_price'] if max_price and min_price else 0
        diff_pct = (price_diff / week_avg * 100) if week_avg > 0 else 0
        
        # 判断是否需要预警（价差超过15%）
        alert_level = 'normal'
        if diff_pct >= 15:
            alert_level = 'high'
        elif diff_pct >= 10:
            alert_level = 'medium'
        
        stats.append({
            'veg_name': veg_name,
            'week_avg': week_avg,
            'total_qty': total_qty,
            'total_amount': total_amount,
            'project_count': len(project_stats),
            'max_price': max_price,
            'min_price': min_price,
            'price_diff': price_diff,
            'diff_pct': diff_pct,
            'alert_level': alert_level,
            'project_stats': sorted_by_price
        })
    
    # 按价差百分比排序（高的在前）
    stats.sort(key=lambda x: x['diff_pct'], reverse=True)
    return stats


def _calculate_project_costs(veg_data, this_week_records, last_week_records):
    """计算各项目采购成本（含上周对比）"""
    project_costs = {}
    
    # 本周数据
    for rec in this_week_records:
        f = rec.get('fields', {})
        project = _get_field_value(f, '项目名称')
        amount = _get_field_value(f, '金额', numeric=True)
        qty = _get_field_value(f, '数量', numeric=True)
        
        if not project:
            continue
        
        if project not in project_costs:
            project_costs[project] = {
                'this_week_amount': 0,
                'this_week_qty': 0,
                'this_week_count': 0,
                'last_week_amount': 0,
                'last_week_qty': 0,
                'alert_count': 0
            }
        
        if amount:
            project_costs[project]['this_week_amount'] += amount
        if qty:
            project_costs[project]['this_week_qty'] += qty
        project_costs[project]['this_week_count'] += 1
    
    # 上周数据
    for rec in last_week_records:
        f = rec.get('fields', {})
        project = _get_field_value(f, '项目名称')
        amount = _get_field_value(f, '金额', numeric=True)
        qty = _get_field_value(f, '数量', numeric=True)
        
        if not project or project not in project_costs:
            continue
        
        if amount:
            project_costs[project]['last_week_amount'] += amount
        if qty:
            project_costs[project]['last_week_qty'] += qty
    
    # 计算异常数
    for veg_name, projects in veg_data.items():
        all_prices = []
        for project, data in projects.items():
            all_prices.extend(data['prices'])
        week_avg = sum(all_prices) / len(all_prices) if all_prices else 0
        
        for project, data in projects.items():
            if project not in project_costs:
                continue
            avg_price = sum(data['prices']) / len(data['prices']) if data['prices'] else 0
            if week_avg > 0 and (avg_price - week_avg) / week_avg >= ALERT_THRESHOLD:
                project_costs[project]['alert_count'] += 1
    
    # 转换为列表并排序
    result = []
    for project, data in project_costs.items():
        this_amount = data['this_week_amount']
        last_amount = data['last_week_amount']
        
        # 计算环比
        week_growth = 0
        if last_amount > 0:
            week_growth = (this_amount - last_amount) / last_amount
        
        result.append({
            'project': project,
            'this_week_amount': this_amount,
            'this_week_qty': data['this_week_qty'],
            'this_week_count': data['this_week_count'],
            'last_week_amount': last_amount,
            'last_week_qty': data['last_week_qty'],
            'alert_count': data['alert_count'],
            'week_growth': week_growth,
            'avg_price': this_amount / data['this_week_qty'] if data['this_week_qty'] > 0 else 0
        })
    
    # 按本周金额排序
    result.sort(key=lambda x: x['this_week_amount'], reverse=True)
    return result


def _calculate_data_completeness(records):
    """计算数据完整度（区分周末休息和缺填）"""
    # 按项目统计本周有数据的天数
    project_days = {}
    
    for rec in records:
        f = rec.get('fields', {})
        project = _get_field_value(f, '项目名称')
        date_val = f.get('日期')
        
        if not project or not date_val:
            continue
        
        if isinstance(date_val, int):
            record_date = datetime.fromtimestamp(date_val / 1000)
        else:
            try:
                record_date = datetime.strptime(str(date_val), '%Y/%m/%d')
            except:
                continue
        
        weekday = record_date.weekday()  # 0=周一, 6=周日
        
        if project not in project_days:
            project_days[project] = set()
        
        project_days[project].add(weekday)
    
    # 计算完整度
    completeness = {}
    for project, days in project_days.items():
        is_weekend_open = PROJECT_WEEKEND_OPEN.get(project, True)
        
        if is_weekend_open:
            # 大学/大专：应该7天都有数据
            expected_days = 7
        else:
            # 初高中：应该只有5天（周一到周五）
            expected_days = 5
        
        actual_days = len(days)
        completeness[project] = {
            'actual_days': actual_days,
            'expected_days': expected_days,
            'completeness_rate': actual_days / expected_days if expected_days > 0 else 0,
            'is_weekend_open': is_weekend_open
        }
    
    return completeness


def _calculate_supplier_stats(veg_data):
    """计算供应商评分：服务项目、异常率、均价偏离、综合评分、等级"""
    supplier_stats = {}
    
    for veg_name, projects in veg_data.items():
        all_prices = []
        for project, data in projects.items():
            all_prices.extend(data['prices'])
        week_avg = sum(all_prices) / len(all_prices) if all_prices else 0
        
        for project, data in projects.items():
            for supplier in data['suppliers']:
                if supplier not in supplier_stats:
                    supplier_stats[supplier] = {
                        'projects': set(),
                        'total_vegs': 0,
                        'alert_vegs': 0,
                        'price_deviations': [],
                        'main_vegs': []
                    }
                
                supplier_stats[supplier]['projects'].add(project)
                supplier_stats[supplier]['total_vegs'] += 1
                supplier_stats[supplier]['main_vegs'].append(veg_name)
                
                avg_price = sum(data['prices']) / len(data['prices']) if data['prices'] else 0
                if week_avg > 0:
                    deviation = (avg_price - week_avg) / week_avg
                    supplier_stats[supplier]['price_deviations'].append(deviation)
                
                if week_avg > 0 and deviation >= ALERT_THRESHOLD:
                    supplier_stats[supplier]['alert_vegs'] += 1
    
    for supplier in supplier_stats:
        total = supplier_stats[supplier]['total_vegs']
        alerts = supplier_stats[supplier]['alert_vegs']
        deviations = supplier_stats[supplier]['price_deviations']
        
        alert_rate = alerts / total if total > 0 else 0
        supplier_stats[supplier]['alert_rate'] = alert_rate
        
        avg_deviation = sum(deviations) / len(deviations) if deviations else 0
        supplier_stats[supplier]['avg_deviation'] = avg_deviation
        
        alert_score = max(0, 40 - alert_rate * 200)
        deviation_score = max(0, 40 - abs(avg_deviation) * 100)
        project_score = min(20, len(supplier_stats[supplier]['projects']) * 10)
        total_score = alert_score + deviation_score + project_score
        supplier_stats[supplier]['score'] = round(total_score)
        
        if total_score >= 85:
            supplier_stats[supplier]['grade'] = 'A ⭐'
        elif total_score >= 70:
            supplier_stats[supplier]['grade'] = 'B'
        elif total_score >= 55:
            supplier_stats[supplier]['grade'] = 'C ⚠️'
        else:
            supplier_stats[supplier]['grade'] = 'D ❌'
        
        supplier_stats[supplier]['projects'] = list(supplier_stats[supplier]['projects'])
        supplier_stats[supplier]['main_vegs'] = list(set(supplier_stats[supplier]['main_vegs']))
    
    return supplier_stats


def _calculate_potential_savings(records):
    """计算潜在节省金额（按本月最低价采购，仅本周数据）"""
    total_savings = 0
    
    actual_cost = {}
    for rec in records:
        f = rec.get('fields', {})
        veg_name = _get_field_value(f, '统一食材名称')
        project = _get_field_value(f, '项目名称')
        amount = _get_field_value(f, '金额', numeric=True)
        qty = _get_field_value(f, '数量', numeric=True)
        month_low = _get_field_value(f, '本月最低价', numeric=True)
        
        if not veg_name or not project:
            continue
        
        if veg_name not in actual_cost:
            actual_cost[veg_name] = {}
        if project not in actual_cost[veg_name]:
            actual_cost[veg_name][project] = {'total_amount': 0, 'total_qty': 0, 'month_low': 0}
        
        actual_cost[veg_name][project]['total_amount'] += (amount or 0)
        actual_cost[veg_name][project]['total_qty'] += (qty or 0)
        if month_low and month_low > 0:
            actual_cost[veg_name][project]['month_low'] = month_low
    
    for veg_name, projects in actual_cost.items():
        all_month_low = [p['month_low'] for p in projects.values() if p['month_low'] > 0]
        if not all_month_low:
            continue
        best_low = min(all_month_low)
        
        for project, data in projects.items():
            if data['month_low'] > 0 and data['total_qty'] > 0:
                actual = data['total_amount']
                ideal = best_low * data['total_qty']
                if actual > ideal:
                    total_savings += (actual - ideal)
    
    return total_savings


# ========== Step 3: 生成分析图表 ==========
def generate_chart(stats):
    """生成TOP10价差食材对比图"""
    print('\n[Step 3] 生成分析图表...')
    import urllib.parse
    
    # 取TOP10（最多10种食材）
    top_stats = stats[:10]
    
    labels = [s['veg_name'] for s in top_stats]
    max_prices = [s['max_price']['avg_price'] if s['max_price'] else 0 for s in top_stats]
    min_prices = [s['min_price']['avg_price'] if s['min_price'] else 0 for s in top_stats]
    week_avgs = [s['week_avg'] for s in top_stats]
    
    chart_config = {
        'type': 'bar',
        'data': {
            'labels': labels,
            'datasets': [
                {'label': '最高单价', 'data': max_prices, 'backgroundColor': '#EF4444'},
                {'label': '近7日均价', 'data': week_avgs, 'backgroundColor': '#F59E0B'},
                {'label': '最低单价', 'data': min_prices, 'backgroundColor': '#10B981'}
            ]
        },
        'options': {
            'title': {'display': True, 'text': 'TOP10 食材跨项目单价对比（近7日均价）'},
            'scales': {
                'yAxes': [{'ticks': {'beginAtZero': True}, 'scaleLabel': {'display': True, 'labelString': '单价（元/斤）'}}]
            },
            'legend': {'position': 'bottom'}
        }
    }
    
    chart_json = json.dumps(chart_config, separators=(',', ':'))
    url = 'https://quickchart.io/chart?w=700&h=400&c=' + urllib.parse.quote(chart_json)
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


# ========== Step 5: 构建分析文本 ==========
def build_analysis_text(stats, project_costs, supplier_stats, potential_savings, data_completeness):
    """构建重点分析和预警文本"""
    lines = []
    
    # 筛选需要预警的（价差>=15%）
    alerts = [s for s in stats if s['alert_level'] == 'high']
    
    # 1. 重点关注（严重超标）— 只显示TOP10
    if alerts:
        lines.append(f"🔴 重点关注（价差≥15%）：共{len(alerts)} 种，以下TOP10")
        lines.append("")
        
        for s in alerts[:10]:  # 只显示TOP10
            veg = s['veg_name']
            max_p = s['max_price']
            min_p = s['min_price']
            
            lines.append(f"【{veg}】近7日均价：¥{s['week_avg']:.2f}/斤，本周采购 {s['total_qty']:.0f}斤 ¥{s['total_amount']:.2f}")
            
            if max_p and min_p:
                lines.append(f"【最高：{max_p['project']} ¥{max_p['avg_price']:.2f}/斤 | 最低：{min_p['project']} ¥{min_p['avg_price']:.2f}/斤】⚠️ 价差：¥{s['price_diff']:.2f}/斤（{s['diff_pct']:.1f}%）")
            lines.append("")
    else:
        lines.append("✅ 本周各项目青菜价格差异正常（价差<15%）")
        lines.append("")
    
    # 2. 供应商评分（无emoji，纯文字）
    if supplier_stats:
        lines.append("🏢 供应商评分：")
        sorted_suppliers = sorted(supplier_stats.items(), key=lambda x: x[1]['score'], reverse=True)
        for supplier, data in sorted_suppliers:
            projects_str = '、'.join(data['projects'])
            alert_rate_str = f"{data['alert_rate']*100:.0f}%"
            deviation_str = f"{data['avg_deviation']*100:+.0f}%"
            grade_clean = data['grade'].replace('⭐', '').replace('⚠️', '').replace('❌', '').strip()
            lines.append(f"  [{grade_clean}] {supplier} | {projects_str} | 异常率 {alert_rate_str} | 均价偏离 {deviation_str} | 评分 {data['score']}")
        lines.append("")
    
    # 3. 项目采购成本TOP5（加上周对比）
    lines.append("💰 项目采购成本 TOP5：")
    for i, p in enumerate(project_costs[:5], 1):
        alert_tag = "🔴" if p['alert_count'] > 0 else "✅"
        
        # 环比涨幅
        growth_str = ""
        if p['last_week_amount'] > 0:
            growth_pct = p['week_growth'] * 100
            if growth_pct > 0:
                growth_str = f" 环比上周 +{growth_pct:.1f}%"
            elif growth_pct < 0:
                growth_str = f" 环比上周 {growth_pct:.1f}%"
            else:
                growth_str = " 环比上周 持平"
        else:
            growth_str = " 上周无数据"
        
        lines.append(f"{i}. {alert_tag} {p['project']}：¥{p['this_week_amount']:.2f}（{p['this_week_qty']:.0f}斤，{p['this_week_count']}笔{'，异常'+str(p['alert_count'])+'种'}{growth_str}）")
    lines.append("")
    
    # 4. 数据完整度监控
    if data_completeness:
        lines.append("📊 数据完整度：")
        for project, data in sorted(data_completeness.items(), key=lambda x: x[1]['completeness_rate']):
            status = "✅" if data['completeness_rate'] >= 0.8 else "⚠️"
            weekend_note = "（周末营业）" if data['is_weekend_open'] else "（周末休息）"
            lines.append(f"  {status} {project}：{data['actual_days']}/{data['expected_days']}天 {weekend_note}")
        lines.append("")
    
    # 5. 潜在节省金额（按本月最低价采购）
    if potential_savings > 0:
        lines.append(f"💸 潜在节省：如果全部按本月最低价采购，本周可节省 ¥{potential_savings:.2f}")
        lines.append(f"   月度预估节省：¥{potential_savings * 4:.2f}")
        lines.append("")
    
    # 6. 建议行动
    lines.append("📋 建议行动：")
    if alerts:
        top_alert = alerts[0]
        lines.append(f"1. 约谈 {top_alert['max_price']['project']}，{top_alert['veg_name']}价格超标{top_alert['diff_pct']:.1f}%")
    if supplier_stats:
        worst_supplier = min(supplier_stats.items(), key=lambda x: x[1]['score'])
        lines.append(f"2. 重点关注 {worst_supplier[0]}（评分{worst_supplier[1]['score']}），异常率{worst_supplier[1]['alert_rate']*100:.0f}%")
        best_supplier = max(supplier_stats.items(), key=lambda x: x[1]['score'])
        lines.append(f"3. 推广 {best_supplier[0]} 经验（评分{best_supplier[1]['score']}），可作为标杆供应商")
    if not alerts:
        lines.append("1. 本周价格稳定，继续保持现有供应商合作")
    
    return '\n'.join(lines)


# ========== Step 6: 发送卡片 ==========
def send_card(token, image_key, stats, project_costs, analysis_text):
    print('\n[Step 5] 发送卡片到群...')
    today = datetime.now().strftime('%Y.%m.%d')
    
    # 计算本周总览
    total_amount = sum(s['total_amount'] for s in stats)
    total_qty = sum(s['total_qty'] for s in stats)
    alert_count = len([s for s in stats if s['alert_level'] == 'high'])
    veg_count = len(stats)
    project_count = len(project_costs)
    
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🥬 青菜价格异常预警周报 · {today}"},
            "template": "green"
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content":
                f"**本周概况**：{project_count}个项目采购 **{veg_count}** 种食材　总量 **{total_qty:.0f}** 斤　金额 **¥{total_amount:.2f}**　🔴 异常 **{alert_count}** 种"}},
            {"tag": "hr"},
            {"tag": "img", "img_key": image_key,
             "alt": {"tag": "plain_text", "content": "食材跨项目单价对比图"},
             "mode": "fit_horizontal", "preview": True},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": analysis_text}},
            {"tag": "hr"},
            {"tag": "note", "elements": [
                {"tag": "plain_text", "content": "数据来源：综合运营管理 Base · 每周五 17:00 自动推送 · 均价为近7日均价 · 预警阈值15%"}]}
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


# ========== Step 7: 归档到多维表格 ==========
def archive_record(token, stats, project_costs, analysis_text, png_bytes):
    print('\n[Step 6] 归档到多维表格...')
    today = datetime.now().strftime('%Y.%m.%d')
    title = f"青菜价格预警周报{today}"
    push_ts = int(time.time() * 1000)
    
    total_amount = sum(s['total_amount'] for s in stats)
    total_qty = sum(s['total_qty'] for s in stats)
    alert_count = len([s for s in stats if s['alert_level'] == 'high'])
    project_count = len(project_costs)
    
    # 上传素材获取 file_token
    print('  [Step 6.1] 上传图表素材...')
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
    
    records_data = [{
        'fields': {
            '标题': title,
            '类别': '每周',
            '推送时间': push_ts,
            '采购总量': total_qty,
            '采购总金额': round(total_amount, 2),
            '异常食材数': alert_count,
            '涉及项目数': project_count,
            '重点关注': analysis_text,
            '分析图表': [{'file_token': file_token}] if file_token else []
        }
    }]
    
    result = api_call('POST',
                       f'/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ARCHIVE}/records/batch_create',
                       token, json_data={'records': records_data})
    record_id = result.get('records', [{}])[0].get('record_id', '')
    print(f"  归档记录已创建: {record_id}")
    return record_id


# ========== 主流程 ==========
def main():
    print('=== 青菜价格异常预警周报 ===\n')
    token = get_tenant_token()
    
    # 预加载供应商名称映射（link 字段只返回 record_id，需要解析）
    supplier_map = fetch_supplier_names(token)
    
    this_week_records, last_week_records = fetch_records(token)
    stats, project_costs, veg_data, data_completeness = parse_and_stats(this_week_records, last_week_records, supplier_map)
    
    if not stats:
        print("本周无青菜采购数据，跳过推送")
        return
    
    # 计算供应商统计和潜在节省
    supplier_stats = _calculate_supplier_stats(veg_data)
    potential_savings = _calculate_potential_savings(this_week_records)
    
    png_bytes = generate_chart(stats)
    image_key = upload_image(token, png_bytes)
    analysis_text = build_analysis_text(stats, project_costs, supplier_stats, potential_savings, data_completeness)
    send_card(token, image_key, stats, project_costs, analysis_text)
    archive_record(token, stats, project_costs, analysis_text, png_bytes)
    
    print('\n=== 全部完成 ===\n')


if __name__ == '__main__':
    for key in ['FEISHU_APP_ID', 'FEISHU_APP_SECRET']:
        if key not in os.environ:
            print(f"错误：环境变量 {key} 未设置")
            sys.exit(1)
    main()
