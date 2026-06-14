# 档口招商周报 — 部署指南

> 两种方式任选其一。推荐使用 **方式二（GitHub Actions）**，完全免维护。

---

## 方式一：WorkBuddy 自动化（公司电脑）

### 前提条件

公司电脑需要：
1. [ ] 已安装 WorkBuddy 客户端
2. [ ] 已加入「推送信息提醒群」（chat_id: `oc_214e828c8acf75a362ca87df4e96eb2e`）
3. [ ] WorkBuddy 中已安装 `lark-base`、`lark-im` 技能

### 部署步骤

1. 将 `weekly_push.py` 和 `data/cards/` 目录复制到公司电脑
2. 在 WorkBuddy 中对话：**"创建自动化，每周五 17:00 执行"**
3. 粘贴以下 prompt（记得把路径改成实际路径）：

```
你是飞书Bot周报推送助手。严格按以下步骤执行：

工作目录: <实际路径，如 D:/工作/周报>
Python路径: C:/Users/<用户名>/.workbuddy/binaries/python/versions/3.13.12/python.exe

步骤1 - 拉取数据:
  在工作目录执行: lark-cli base +record-list --as user --base-token CWRUbNJLZa5BmSsuWx1cvcoFnsd --table-id tblLiIxSybeE9AfV --limit 200 --format json > data/raw_data.json

步骤2 - 生成图表+卡片:
  在工作目录执行: <Python路径> weekly_push.py

步骤3 - 上传图表:
  在工作目录执行: lark-cli im images create --as bot --data '{"image_type":"message"}' --file image=chart_tmp.png
  提取 image_key。

步骤4 - 发送卡片:
  用Python将 data/cards/weekly_merged.json 中的 IMG_KEY_PLACEHOLDER 替换为 image_key，
  然后执行: lark-cli im +messages-send --as bot --chat-id oc_214e828c8acf75a362ca87df4e96eb2e --msg-type interactive --content '<替换后的JSON>'

步骤5 - 归档:
  读取 data/archive_info.json，用 lark-cli base +record-upsert 写入「档口」招商周报表。
  然后执行: lark-cli base +record-upload-attachment --as user --base-token CWRUbNJLZa5BmSsuWx1cvcoFnsd --table-id tblBBBfEpOKGPSkA --field-id fldxPLOcoS --file chart_tmp.png

完成后报告"推送+归档完成"。
```

---

## 方式二：GitHub Actions（推荐，云端运行）

### 原理

```
GitHub Actions（免费Runner）
    │
    ├─ 每周五 17:00 北京时间自动触发
    ├─ 运行 weekly_push_http.py
    ├─ 调用飞书 OpenAPI（纯 HTTP）
    ├─ 推送卡片到群
    └─ 归档到多维表格
```

**不需要**公司电脑开机，不需要 WorkBuddy 客户端。

### 第一步：获取飞书应用凭证

1. 登录 [飞书开放平台](https://open.feishu.cn/app)（用你的飞书账号）
2. 找到应用 **cli_aa942da6d3381bd7**（或新建一个企业自建应用）
3. 进入 **凭证与基础信息** → 复制：
   - `App ID`
   - `App Secret`
4. 在 **权限管理** 中开通以下权限：
   - `bitable:record`（读写多维表格）
   - `im:message`（发送消息）
   - `im:image`（上传图片）
5. 在 **应用发布** 中发布应用（至少启用）

### 第二步：创建 GitHub 仓库

```bash
# 在公司电脑或任意机器上
mkdir dangkou-report && cd dangkou-report
git init
# 把以下文件复制进来：
#   weekly_push_http.py
#   requirements.txt
#   .github/workflows/weekly_report.yml
git add .
git commit -m "init"
git remote add origin https://github.com/<你的用户名>/dangkou-report.git
git push -u origin main
```

### 第三步：设置 GitHub Secrets

进入仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：

| Secret 名称 | 值 |
|-------------|-----|
| `FEISHU_APP_ID` | 第一步获取的 App ID |
| `FEISHU_APP_SECRET` | 第一步获取的 App Secret |
| `FEISHU_CHAT_ID` | `oc_214e828c8acf75a362ca87df4e96eb2e` |

### 第四步：启用 Workflow

进入仓库 → **Actions** 标签页 → 找到 `档口招商周报推送` → 点击 **Enable workflow**。

### 第五步：手动触发测试

进入仓库 → **Actions** → 选择 `档口招商周报推送` → 点击 **Run workflow** → 选择 `main` 分支 → 确认。

等待约 1-2 分钟，群里应收到周报卡片。

---

## 关键信息速查

| 项目 | 值 |
|------|-----|
| Base Token | `CWRUbNJLZa5BmSsuWx1cvcoFnsd` |
| 班组表 | `tblLiIxSybeE9AfV` |
| 归档表 | `tblBBBfEpOKGPSkA` |
| 推送群 chat_id | `oc_214e828c8acf75a362ca87df4e96eb2e` |
| Bot App ID | `cli_aa942da6d3381bd7` |

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `weekly_push.py` | 方式一用（依赖 lark-cli） |
| `weekly_push_http.py` | 方式二用（纯 HTTP，无依赖） |
| `requirements.txt` | Python 依赖（`requests`） |
| `.github/workflows/weekly_report.yml` | GitHub Actions 配置 |
| `setup.md` | 本说明文件 |
