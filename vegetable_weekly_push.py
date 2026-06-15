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

# 食材 option_id → 中文名称 映射（来自「产品-基础信息」表的 🚩统一食材名称 单选字段）
VEG_OPTION_MAP = {
    'optxnIDAr4': '蒜苗', 'optoLQBaYU': '木耳', 'opttI0zlHo': '红薯', 'optW8zrvBY': '线椒',
    'optPmfP6mD': '大葱', 'optWK0nlgn': '香菇', 'optwv9NC7y': '红椒', 'optXhOAzHq': '空心菜',
    'optkpfTVvy': '包菜', 'optrJurwWg': '白菜', 'opt7Z9cAi6': '油麦菜', 'optbjmGruw': '平菇',
    'optT5zv6sT': '苋菜', 'optSmkfazk': '芋头', 'optefnWplj': '洋葱', 'optYUKWYZz': '酸菜',
    'optIgNjxGO': '南瓜', 'optdRpoIyU': '紫甘蓝', 'optnoRJaZ0': '芹菜', 'opteQRwQyz': '鹿茸菇',
    'opts9C57FI': '葱', 'optyX3oDCR': '土豆', 'optlSdLZ7v': '莴笋', 'optG5RBhSP': '黄豆芽',
    'optJ0W8826': '土茯苓', 'optddgGxBw': '蒜苔', 'optc8Wpc6M': '小白菜', 'optvlHiZbo': '娃娃菜',
    'optfZstJUb': '西葫芦', 'optBdAP3UX': '花菜', 'opt8IguVtS': '莲子', 'optgEZEKDi': '奶白菜',
    'optdh6NFql': '金针菇', 'optjhAoTdd': '蒜', 'optLqhJbIx': '韭菜', 'opt1rWQe8c': '青豆',
    'optujv2pKC': '茄子', 'optF1r272D': '生菜', 'optLz8pRWo': '海带', 'opt8OHAyEg': '白萝卜',
    'optxNIOUvr': '西洋菜', 'optYTIrcOv': '上海青', 'optWe6xbzc': '姜', 'optESB4rln': '青椒',
    'optu45vAt4': '荷兰豆', 'optPB9GxL8': '木瓜', 'optIjAW47o': '小米椒', 'optb9PmOvR': '香菜',
    'optQtAyCBq': '节瓜', 'opt7IzNZYw': '豆泡', 'opttxpQ1Rf': '菜心', 'opt2RT4ZhM': '葱头',
    'optx6GTS7B': '丝瓜', 'optq8ExNL8': '苦瓜', 'opt4Ndrqno': '杏鲍菇', 'optiCX1Cv2': '山药',
    'optVjSY6QI': '花椒', 'opt5nxC5O4': '海鲜菇', 'optnnyqgmX': '秋葵', 'optLW5v4EG': '沙姜',
    'optSukrfh2': '豆角', 'opteLhmugr': '黄瓜', 'opthEbDgzn': '胡萝卜', 'optIHC7j1g': '冬瓜',
    'optHIL4aWF': '西兰花', 'optx4q8kQq': '甜瓜', 'opt2kE7a1a': '芥菜', 'optTLfxt3i': '西生菜',
    'optqk7UA2p': '豆腐', 'optXf88dbQ': '莲藕', 'optO8Vo3x7': '蒲瓜', 'optC1itu3k': '茶树菇',
    'opt1sJXUnU': '菠菜', 'optMTqIGpA': '韭黄', 'opt0KWYS6q': '香干', 'optqUflMuc': '西红柿',
    'optzJqJMjc': '春菜', 'optrrCzKfN': '圆椒', 'optgKk71Xi': '秀珍菇', 'opt7BrX5WY': '白瓜',
    'optOBoOHSC': '绿豆芽', 'optV9qK5sm': '紫薯', 'optvd8TCoz': '枸杞叶', 'optTf5I88A': '白玉菇',
    'optSMVomjR': '彩椒', 'optH3vxf86': '豆苗', 'optEP3qcP7': '苦麦菜', 'opt9lnG1Bp': '葫芦瓜',
    'optnCkCATl': '菠萝', 'optqUy0bEk': '番薯叶', 'opthDLxWjc': '儿菜', 'optHg3Ryak': '紫苏',
    'optikLjOdU': '青菜',
}

# 项目类型配置（周末是否营业）
# 用户确认：除连平中学外，其他都是大学/大专，周末均营业
PROJECT_WEEKEND_OPEN = {
    '嘉应学院': True,      # 大学，周末营业
    '天河交通': True,      # 大专，周末营业
    '花都工商': True,      # 大学/大专，周末营业
    '清远建设': True,      # 大学/大专，周末营业
    '清远交通': True,      # 大专，周末营业
    '连平中学': False,     # 高中，偶尔双休
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
        
        # 调试：打印第一条记录中关键字段的原始值
        if items and not page_token:
            debug_fields = items[0].get('fields', {})
            _log(f"[DEBUG] 统一食材名称原始值: {repr(debug_fields.get('统一食材名称'))}")
            _log(f"[DEBUG] 项目名称原始值: {repr(debug_fields.get('项目名称'))}")
            _log(f"[DEBUG] 供应商名称原始值: {repr(debug_fields.get('供应商名称'))}")
        
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
    """从 fields 中提取字段值，兼容飞书所有字段类型。"""
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
        return ids[0] if ids else None

    # 列表类型（多选/关联等）
    if isinstance(val, list):
        val = val[0] if val else None

    if val is None:
        return None

    # dict 类型兜底（单选等）
    if isinstance(val, dict):
        val = val.get('text') or val.get('id', '')

    # 若拿到的是 option_id，通过映射表解析为中文
    if isinstance(val, str) and val.startswith('opt'):
        mapped = VEG_OPTION_MAP.get(val)
        if mapped:
            val = mapped
        # 如果映射表没有，保留原始值（可能是新增的食材选项）

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
    """计算各项目本周实际填报天数"""
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
        
        if project not in project_days:
            project_days[project] = set()
        
        project_days[project].add(record_date.strftime('%m/%d'))
    
    # 统计实际填报天数
    completeness = {}
    for project, days in project_days.items():
        actual_days = len(days)
        completeness[project] = {
            'actual_days': actual_days,
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
def generate_chart(stats, project_costs):
    """生成四合一数据分析看板（2x2布局 + 数据标签）"""
    print('\n[Step 3] 生成分析图表...')
    import urllib.parse
    from PIL import Image, ImageDraw, ImageFont
    import math

    # ========== 图1: TOP10食材单价对比 ==========
    top10 = stats[:10]
    labels1 = [s['veg_name'] for s in top10]
    max_p = [s['max_price']['avg_price'] if s['max_price'] else 0 for s in top10]
    avg_p = [s['week_avg'] for s in top10]
    min_p = [s['min_price']['avg_price'] if s['min_price'] else 0 for s in top10]

    chart1 = {
        'type': 'bar',
        'data': {
            'labels': labels1,
            'datasets': [
                {'label': '最高', 'data': max_p, 'backgroundColor': '#EF4444'},
                {'label': '均价', 'data': avg_p, 'backgroundColor': '#F59E0B'},
                {'label': '最低', 'data': min_p, 'backgroundColor': '#10B981'}
            ]
        },
        'options': {
            'title': {'display': True, 'text': 'TOP10食材单价对比（元/斤）', 'fontSize': 13, 'fontColor': '#333'},
            'scales': {
                'yAxes': [{'ticks': {'beginAtZero': True, 'fontColor': '#666', 'stepSize': 2}, 'gridLines': {'color': 'rgba(0,0,0,0.05)'}}],
                'xAxes': [{'ticks': {'fontColor': '#333', 'fontSize': 10}, 'gridLines': {'display': False}}]
            },
            'legend': {'position': 'bottom', 'labels': {'fontColor': '#333', 'fontSize': 9, 'padding': 8}}
        }
    }
    url1 = 'https://quickchart.io/chart?w=520&h=340&bkg=white&c=' + urllib.parse.quote(json.dumps(chart1, separators=(',', ':')))
    img1_bytes = requests.get(url1, timeout=30).content
    img1 = Image.open(io.BytesIO(img1_bytes))

    # ========== 图2: 采购数量TOP5 ==========
    sorted_by_qty = sorted(stats, key=lambda x: x['total_qty'], reverse=True)
    top5_qty = sorted_by_qty[:5]
    labels2 = [s['veg_name'] for s in top5_qty]
    qty2 = [s['total_qty'] for s in top5_qty]
    colors2 = ['#EF4444', '#F59E0B', '#3B82F6', '#8B5CF6', '#10B981']

    chart2 = {
        'type': 'bar',
        'data': {
            'labels': labels2,
            'datasets': [{'data': qty2, 'backgroundColor': colors2}]
        },
        'options': {
            'title': {'display': True, 'text': '本周采购数量TOP5（斤）', 'fontSize': 13, 'fontColor': '#333'},
            'scales': {
                'yAxes': [{'ticks': {'beginAtZero': True, 'fontColor': '#666'}, 'gridLines': {'color': 'rgba(0,0,0,0.05)'}}],
                'xAxes': [{'ticks': {'fontColor': '#333'}, 'gridLines': {'display': False}}]
            },
            'legend': {'display': False}
        }
    }
    url2 = 'https://quickchart.io/chart?w=520&h=340&bkg=white&c=' + urllib.parse.quote(json.dumps(chart2, separators=(',', ':')))
    img2_bytes = requests.get(url2, timeout=30).content
    img2 = Image.open(io.BytesIO(img2_bytes))

    # ========== 图3: 项目采购金额占比饼图 ==========
    sorted_projects = sorted(project_costs, key=lambda x: x['this_week_amount'], reverse=True)
    labels3 = [p['project'] for p in sorted_projects]
    amt3 = [p['this_week_amount'] for p in sorted_projects]
    colors3 = ['#4472C4', '#70AD47', '#FFC000', '#ED7D31', '#9E480E', '#5B9BD5', '#A5A5A5', '#7030A0', '#C55A11', '#2F5597']

    chart3 = {
        'type': 'pie',
        'data': {'labels': labels3, 'datasets': [{'data': amt3, 'backgroundColor': colors3[:len(amt3)], 'borderColor': '#fff', 'borderWidth': 2}]},
        'options': {
            'title': {'display': True, 'text': '各项目采购金额占比', 'fontSize': 13, 'fontColor': '#333'},
            'legend': {'position': 'right', 'labels': {'fontColor': '#333', 'fontSize': 9, 'padding': 6}}
        }
    }
    url3 = 'https://quickchart.io/chart?w=520&h=340&bkg=white&c=' + urllib.parse.quote(json.dumps(chart3, separators=(',', ':')))
    img3_bytes = requests.get(url3, timeout=30).content
    img3 = Image.open(io.BytesIO(img3_bytes))

    # ========== 图4: 重点关注食材价差对比 ==========
    alerts = [s for s in stats if s['alert_level'] == 'high'][:5]
    if not alerts:
        alerts = stats[:5]
    labels4 = [s['veg_name'] for s in alerts]
    max4 = [s['max_price']['avg_price'] if s['max_price'] else 0 for s in alerts]
    min4 = [s['min_price']['avg_price'] if s['min_price'] else 0 for s in alerts]

    chart4 = {
        'type': 'bar',
        'data': {
            'labels': labels4,
            'datasets': [
                {'label': '最高', 'data': max4, 'backgroundColor': '#EF4444'},
                {'label': '最低', 'data': min4, 'backgroundColor': '#10B981'}
            ]
        },
        'options': {
            'title': {'display': True, 'text': '重点关注食材价差对比（元/斤）', 'fontSize': 13, 'fontColor': '#333'},
            'scales': {
                'yAxes': [{'ticks': {'beginAtZero': True, 'fontColor': '#666'}, 'gridLines': {'color': 'rgba(0,0,0,0.05)'}}],
                'xAxes': [{'ticks': {'fontColor': '#333'}, 'gridLines': {'display': False}}]
            },
            'legend': {'position': 'bottom', 'labels': {'fontColor': '#333', 'fontSize': 9, 'padding': 8}}
        }
    }
    url4 = 'https://quickchart.io/chart?w=520&h=340&bkg=white&c=' + urllib.parse.quote(json.dumps(chart4, separators=(',', ':')))
    img4_bytes = requests.get(url4, timeout=30).content
    img4 = Image.open(io.BytesIO(img4_bytes))

    # ========== 合并为 2x2 大图 + 添加数据标签 ==========
    w, h = 520, 340
    title_h = 55
    pad = 12
    total_w = w * 2 + pad * 3
    total_h = h * 2 + pad * 3 + title_h

    merged = Image.new('RGB', (total_w, total_h), '#FFFFFF')
    draw = ImageDraw.Draw(merged)

    # 加载字体
    try:
        font_title = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 22)
        font_label = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 9)
        font_small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 8)
        font_pct = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 10)
    except:
        font_title = font_label = font_small = font_pct = ImageFont.load_default()

    # 标题
    draw.text((total_w // 2, 18), "青菜价格异常预警周报 - 数据分析看板", fill='#1a1a1a', font=font_title, anchor='mt')

    # 放置四张图
    pos1 = (pad, title_h + pad)
    pos2 = (w + pad * 2, title_h + pad)
    pos3 = (pad, title_h + h + pad * 2)
    pos4 = (w + pad * 2, title_h + h + pad * 2)
    merged.paste(img1, pos1)
    merged.paste(img2, pos2)
    merged.paste(img3, pos3)
    merged.paste(img4, pos4)

    # --- 图1 数据标签 ---
    y_max1 = max(max(max_p), 1)
    y_scale1 = 14 if y_max1 <= 14 else (y_max1 * 1.15)
    cx1, cy1 = pos1
    bar_w, group_w = 11, 42
    sx1 = cx1 + 52
    by1 = cy1 + 278
    yr1 = 240
    for i, (mx, av, mn) in enumerate(zip(max_p, avg_p, min_p)):
        gx = sx1 + i * group_w
        draw.text((gx + 2, by1 - (mx / y_scale1) * yr1 - 3), f'{mx:.1f}', fill='#333', font=font_label, anchor='mb')
        draw.text((gx + bar_w + 3, by1 - (av / y_scale1) * yr1 - 3), f'{av:.1f}', fill='#B45309', font=font_small, anchor='mb')
        draw.text((gx + bar_w * 2 + 5, by1 - (mn / y_scale1) * yr1 - 3), f'{mn:.1f}', fill='#059669', font=font_small, anchor='mb')

    # --- 图2 数据标签 ---
    y_max2 = max(max(qty2), 1)
    y_scale2 = y_max2 * 1.15
    cx2, cy2 = pos2
    sx2 = cx2 + 58
    gw2 = 82
    by2 = cy2 + 278
    yr2 = 240
    for i, q in enumerate(qty2):
        gx = sx2 + i * gw2 + 30
        draw.text((gx, by2 - (q / y_scale2) * yr2 - 5), f'{q:.0f}斤', fill='#333', font=font_label, anchor='mb')

    # --- 图3 饼图百分比标签 ---
    cx3, cy3 = pos3
    pcx, pcy = cx3 + 155, cy3 + 170
    pr = 100
    total_amt = sum(amt3)
    angle = -90
    for amt_val, col in zip(amt3, colors3[:len(amt3)]):
        pct = amt_val / total_amt if total_amt > 0 else 0
        sweep = pct * 360
        ma = angle + sweep / 2
        rad = math.radians(ma)
        lx = pcx + pr * 0.6 * math.cos(rad)
        ly = pcy + pr * 0.6 * math.sin(rad)
        txt = f'{pct * 100:.1f}%'
        bbox = draw.textbbox((0, 0), txt, font=font_pct)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.rectangle([lx - tw / 2 - 2, ly - th / 2 - 1, lx + tw / 2 + 2, ly + th / 2 + 1], fill=col)
        draw.text((lx, ly), txt, fill='#FFFFFF', font=font_pct, anchor='mm')
        angle += sweep

    # --- 图4 数据标签 + 价差 ---
    y_max4 = max(max(max4), 1)
    y_scale4 = 14 if y_max4 <= 14 else (y_max4 * 1.15)
    cx4, cy4 = pos4
    sx4 = cx4 + 65
    gw4 = 82
    by4 = cy4 + 278
    yr4 = 240
    for i, (mx, mn) in enumerate(zip(max4, min4)):
        gx = sx4 + i * gw4 + 22
        hy = by4 - (mx / y_scale4) * yr4 - 3
        ly = by4 - (mn / y_scale4) * yr4 - 3
        draw.text((gx, hy), f'{mx:.1f}', fill='#333', font=font_label, anchor='mb')
        draw.text((gx + 30, ly), f'{mn:.1f}', fill='#059669', font=font_small, anchor='mb')
        diff = ((mx - mn) / mn * 100) if mn > 0 else 0
        draw.text((gx + 15, (hy + ly) / 2 - 5), f'价差{diff:.0f}%', fill='#DC2626', font=font_small, anchor='mm')

    # 分隔线
    draw.line([(total_w // 2, title_h), (total_w // 2, total_h)], fill='#E5E5E5', width=1)
    draw.line([(0, title_h + h + pad), (total_w, title_h + h + pad)], fill='#E5E5E5', width=1)

    # 输出为 PNG bytes
    buf = io.BytesIO()
    merged.save(buf, format='PNG', quality=95)
    png_bytes = buf.getvalue()
    print(f"  看板大小: {len(png_bytes) // 1024} KB")
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
    
    # 1. 重点关注：按采购数量排序，展示数量TOP10食材的价差情况
    # 这样更有实际参考价值——数量多的食材价格波动对成本影响更大
    sorted_by_qty = sorted(stats, key=lambda x: x['total_qty'], reverse=True)
    top10_qty = sorted_by_qty[:10]
    
    # 从中筛选出差价>=15%的
    alerts_in_top10 = [s for s in top10_qty if s['alert_level'] == 'high']
    
    if alerts_in_top10:
        lines.append(f"🔴 重点关注（采购数量TOP10中价差≥15%）：共{len(alerts_in_top10)} 种")
        lines.append("")
        
        for s in alerts_in_top10:
            veg = s['veg_name']
            max_p = s['max_price']
            min_p = s['min_price']
            
            lines.append(f"【{veg}】本周采购 {s['total_qty']:.0f}斤 ¥{s['total_amount']:.2f} | 均价¥{s['week_avg']:.2f}/斤")
            
            if max_p and min_p:
                lines.append(f"  最高：{max_p['project']} ¥{max_p['avg_price']:.2f}/斤 | 最低：{min_p['project']} ¥{min_p['avg_price']:.2f}/斤")
                lines.append(f"  ⚠️ 价差：¥{s['price_diff']:.2f}/斤（{s['diff_pct']:.1f}%）")
            lines.append("")
    else:
        lines.append("✅ 本周采购数量TOP10食材价格差异正常（价差<15%）")
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
    
    # 3. 采购数量TOP5
    sorted_by_qty = sorted(stats, key=lambda x: x['total_qty'], reverse=True)
    lines.append("📦 采购数量TOP5：")
    for i, s in enumerate(sorted_by_qty[:5], 1):
        veg = s['veg_name']
        qty = s['total_qty']
        amount = s['total_amount']
        avg = s['week_avg']
        lines.append(f"  {i}. {veg}：{qty:.0f}斤 ¥{amount:.2f}（均价¥{avg:.2f}/斤）")
    lines.append("")

    # 4. 项目采购成本TOP5（加上周对比）
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

    # 5. 项目异常食材TOP5（按异常食材数量排序）
    projects_with_alerts = [p for p in project_costs if p.get('alert_count', 0) > 0]
    if projects_with_alerts:
        sorted_by_alerts = sorted(projects_with_alerts, key=lambda x: x['alert_count'], reverse=True)
        lines.append("⚠️ 项目异常食材TOP5（价差≥15%的食材数量）：")
        for i, p in enumerate(sorted_by_alerts[:5], 1):
            alert_count = p['alert_count']
            lines.append(f"  {i}. {p['project']}：{alert_count}种食材异常（总采购¥{p['this_week_amount']:.2f}）")
        lines.append("")
    else:
        lines.append("✅ 本周各项目无异常食材")
        lines.append("")

    # 6. 数据完整度监控
    if data_completeness:
        lines.append("📊 本周填报情况：")
        for project, data in sorted(data_completeness.items(), key=lambda x: x[1]['actual_days']):
            days = data['actual_days']
            if days >= 7:
                status = "✅"
            elif days >= 5:
                status = "⚠️"
            else:
                status = "🔴"
            lines.append(f"  {status} {project}：已填报 {days} 天")
        lines.append("")
    
    # 7. 潜在节省金额（按本月最低价采购）
    if potential_savings > 0:
        lines.append(f"💸 潜在节省：如果全部按本月最低价采购，本周可节省 ¥{potential_savings:.2f}")
        lines.append(f"   月度预估节省：¥{potential_savings * 4:.2f}")
        lines.append("")
    
    # 8. 建议行动
    lines.append("📋 建议行动：")
    if alerts_in_top10:
        top_alert = alerts_in_top10[0]
        lines.append(f"1. 约谈 {top_alert['max_price']['project']}，{top_alert['veg_name']}采购{top_alert['total_qty']:.0f}斤价格超标{top_alert['diff_pct']:.1f}%")
    if supplier_stats:
        worst_supplier = min(supplier_stats.items(), key=lambda x: x[1]['score'])
        lines.append(f"2. 重点关注 {worst_supplier[0]}（评分{worst_supplier[1]['score']}），异常率{worst_supplier[1]['alert_rate']*100:.0f}%")
        best_supplier = max(supplier_stats.items(), key=lambda x: x[1]['score'])
        lines.append(f"3. 推广 {best_supplier[0]} 经验（评分{best_supplier[1]['score']}），可作为标杆供应商")
    if not alerts_in_top10:
        lines.append("1. 本周采购量大的食材价格稳定，继续保持现有供应商合作")
    
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
    stats, project_costs, veg_data, data_completeness = parse_and_stats(
        this_week_records, last_week_records, supplier_map)
    
    if not stats:
        print("本周无青菜采购数据，跳过推送")
        return
    
    # 计算供应商统计和潜在节省
    supplier_stats = _calculate_supplier_stats(veg_data)
    potential_savings = _calculate_potential_savings(this_week_records)
    
    png_bytes = generate_chart(stats, project_costs)
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
