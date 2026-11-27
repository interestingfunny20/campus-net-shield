"""
网安老师 Web 后台：拦截记录、热门钓鱼类型、每周趋势

运行：python server.py
访问：http://127.0.0.1:5000
"""
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "guard.db")


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-XSS-Protection"] = "1; mode=block"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            host TEXT,
            level TEXT,
            score INTEGER,
            reason TEXT,
            source TEXT DEFAULT 'extension',
            reported_at TEXT
        )
    """)
    # 兼容老库：如果 reports 表没有 source 列，补上
    c.execute("PRAGMA table_info(reports)")
    cols = [row[1] for row in c.fetchall()]
    if "source" not in cols:
        c.execute("ALTER TABLE reports ADD COLUMN source TEXT DEFAULT 'extension'")
    conn.commit()
    conn.close()


@app.route("/api/report", methods=["POST"])
def report():
    data = request.get_json(force=True) or {}
    # 输入校验 + 长度截断，防注入和超长字段
    def s(key, n=200):
        v = str(data.get(key, ""))
        return v[:n]
    level = s("level", 10)
    if level not in ("高危", "可疑", "安全", "未知"):
        level = "未知"
    source = s("source", 20)
    if source not in ("desktop", "extension"):
        source = "extension"
    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except Exception:
        score = 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO reports (url, host, level, score, reason, source, reported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        s("url", 500),
        s("host", 200),
        level,
        score,
        s("reason", 500),
        source,
        s("time", 40) or datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/stats")
def stats():
    days = request.args.get("days", "7")
    page = int(request.args.get("page", "1"))
    per_page = int(request.args.get("per_page", "20"))
    level_filter = request.args.get("level", "")
    host_filter = request.args.get("host", "")

    try:
        days_int = int(days) if days != "all" else 3650
    except ValueError:
        days_int = 7

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM reports")
    total = c.fetchone()[0]

    c.execute("SELECT level, COUNT(*) FROM reports GROUP BY level")
    level_dist = {row[0]: row[1] for row in c.fetchall()}

    c.execute("SELECT source, COUNT(*) FROM reports GROUP BY source")
    source_dist = {row[0]: row[1] for row in c.fetchall()}

    today = datetime.now().date().isoformat()
    c.execute("SELECT COUNT(*) FROM reports WHERE date(reported_at) = ?", (today,))
    today_count = c.fetchone()[0]

    # 最近 N 天每天的拦截数
    daily = []
    for i in range(days_int - 1, -1, -1):
        day = (datetime.now().date() - timedelta(days=i)).isoformat()
        c.execute("""
            SELECT level, COUNT(*) FROM reports
            WHERE date(reported_at) = ?
            GROUP BY level
        """, (day,))
        rows = c.fetchall()
        day_data = {"date": day[5:]}
        for level, cnt in rows:
            day_data[level] = cnt
        daily.append(day_data)

    c.execute("""
        SELECT host, COUNT(*) as cnt FROM reports
        WHERE level IN ('高危', '可疑')
        GROUP BY host ORDER BY cnt DESC LIMIT 10
    """)
    top_hosts = [{"host": row[0], "count": row[1]} for row in c.fetchall()]

    # 分页查询（带等级和域名筛选）
    where = "WHERE 1=1"
    params = []
    if level_filter:
        where += " AND level = ?"
        params.append(level_filter)
    if host_filter:
        where += " AND host LIKE ?"
        params.append(f"%{host_filter}%")

    c.execute(f"SELECT COUNT(*) FROM reports {where}", params)
    total_records = c.fetchone()[0]

    offset = (page - 1) * per_page
    c.execute(f"""
        SELECT host, level, score, reason, source, reported_at FROM reports
        {where}
        ORDER BY id DESC LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    recent = [
        {
            "host": row[0],
            "level": row[1],
            "score": row[2],
            "reason": row[3],
            "source": row[4] or "extension",
            "time": row[5],
        }
        for row in c.fetchall()
    ]

    conn.close()
    return jsonify({
        "total": total,
        "today_count": today_count,
        "level_dist": level_dist,
        "source_dist": source_dist,
        "daily": daily,
        "top_hosts": top_hosts,
        "recent": recent,
        "total_records": total_records,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_records + per_page - 1) // per_page,
    })


@app.route("/api/export.csv")
def export_csv():
    """导出全部记录为 CSV"""
    import csv
    import io
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT url, host, level, score, reason, source, reported_at FROM reports ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM 让 Excel 正确识别 UTF-8
    w = csv.writer(buf)
    w.writerow(["URL", "网站", "等级", "得分", "原因", "来源", "时间"])
    for r in rows:
        w.writerow(r)
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=reports.csv"})


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>校园钓鱼检测后台</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: "Microsoft YaHei", "PingFang SC", -apple-system, sans-serif; background: #f3f4f6; color: #1f2937; }

  /* ===== 顶部导航 ===== */
  .topbar { background: #111827; color: #fff; padding: 0 32px; height: 56px;
            display: flex; align-items: center; justify-content: space-between; }
  .topbar .left { display: flex; align-items: center; gap: 28px; }
  .topbar .logo { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .topbar .logo .shield { color: #ef4444; }
  .topbar nav { display: flex; gap: 4px; }
  .topbar nav a { color: #9ca3af; text-decoration: none; padding: 6px 14px; font-size: 14px;
                  border-radius: 6px; cursor: pointer; }
  .topbar nav a.active { color: #fff; background: rgba(255,255,255,0.08); }
  .topbar nav a:hover { color: #fff; }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .topbar .right { font-size: 13px; color: #9ca3af; }

  .container { max-width: 1440px; margin: 0 auto; padding: 24px 32px; }

  /* ===== 核心指标行 ===== */
  .kpi-row { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .kpi { background: #fff; border-radius: 10px; padding: 20px 22px;
         box-shadow: 0 1px 2px rgba(0,0,0,0.04); border: 1px solid #e5e7eb; }
  .kpi .label { font-size: 13px; color: #6b7280; margin-bottom: 8px; }
  .kpi .value { font-size: 36px; font-weight: 700; line-height: 1; }
  .kpi .sub { font-size: 12px; color: #9ca3af; margin-top: 8px; }
  .kpi.kpi-highlight { background: linear-gradient(135deg, #dc2626, #b91c1c); border: none; }
  .kpi.kpi-highlight .label, .kpi.kpi-highlight .sub { color: #fecaca; }
  .kpi.kpi-highlight .value { color: #fff; }
  .kpi.warn .value { color: #d97706; }
  .kpi.neutral .value { color: #1f2937; }
  .kpi.total .value { color: #6b7280; }

  /* ===== 图表区：主图 + 副图 ===== */
  .row-main { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
  .row-sub { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
  .card { background: #fff; border-radius: 10px; padding: 20px;
          border: 1px solid #e5e7eb; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
  .card h3 { font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 14px;
             display: flex; align-items: center; justify-content: space-between; }
  .card h3 .hint { font-size: 12px; color: #9ca3af; font-weight: normal; }

  /* ===== 表格区 ===== */
  .table-card { background: #fff; border-radius: 10px; border: 1px solid #e5e7eb;
                box-shadow: 0 1px 2px rgba(0,0,0,0.04); overflow: hidden; }
  .table-toolbar { display: flex; gap: 10px; padding: 16px 20px; align-items: center;
                   border-bottom: 1px solid #f3f4f6; }
  .table-toolbar h3 { font-size: 15px; font-weight: 600; }
  .table-toolbar .spacer { flex: 1; }
  .table-toolbar select, .table-toolbar input {
      padding: 7px 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; background: #fff; }
  .table-toolbar button {
      padding: 7px 16px; background: #dc2626; color: #fff; border: none;
      border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
  .table-toolbar button:hover { background: #b91c1c; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 12px 20px; text-align: left; font-size: 13px; }
  th { background: #f9fafb; color: #6b7280; font-weight: 500; font-size: 12px;
       text-transform: uppercase; letter-spacing: 0.5px; }
  tr + tr td { border-top: 1px solid #f3f4f6; }
  tbody tr:hover { background: #f9fafb; }

  .level { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .level-high { background: #fee2e2; color: #dc2626; }
  .level-susp { background: #fef3c7; color: #d97706; }
  .level-safe { background: #dcfce7; color: #16a34a; }
  .level-unknown { background: #f3f4f6; color: #6b7280; }
  .src { font-size: 12px; color: #6b7280; }
  .src .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; }
  .src-desktop .dot { background: #dc2626; }
  .src-ext .dot { background: #3b82f6; }

  /* 时间范围按钮 */
  .range-btn { padding: 3px 10px; margin-left: 4px; border: 1px solid #d1d5db;
    background: #fff; border-radius: 4px; font-size: 12px; cursor: pointer; color: #6b7280; }
  .range-btn.active { background: #dc2626; color: #fff; border-color: #dc2626; }

  /* 分页 */
  .pagination { display: flex; gap: 8px; align-items: center; justify-content: flex-end;
    padding: 12px 20px; border-top: 1px solid #f3f4f6; font-size: 13px; }
  .pagination button { padding: 5px 12px; border: 1px solid #d1d5db; background: #fff;
    border-radius: 4px; cursor: pointer; font-size: 13px; }
  .pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
  .pagination button:not(:disabled):hover { background: #f3f4f6; }
  .pagination .page-info { color: #6b7280; }
</style>
</head>
<body>
<div class="topbar">
  <div class="left">
    <div class="logo"><span class="shield">🛡</span> 校园钓鱼检测后台</div>
    <nav>
      <a data-tab="dashboard" class="active">数据总览</a>
      <a data-tab="records">检测记录</a>
      <a data-tab="alerts">告警管理</a>
      <a data-tab="settings">系统设置</a>
    </nav>
  </div>
  <div class="right" id="clock">--</div>
</div>

<div class="container">
  <!-- 数据总览 Tab -->
  <div class="tab-pane active" id="tab-dashboard">
  <!-- KPI 行：突出今日高危 -->
  <div class="kpi-row">
    <div class="kpi kpi-highlight">
      <div class="label">今日高危网站</div>
      <div class="value" id="todayHigh">0</div>
      <div class="sub">需要立即处置</div>
    </div>
    <div class="kpi warn">
      <div class="label">今日可疑网站</div>
      <div class="value" id="todaySusp">0</div>
      <div class="sub">建议复核</div>
    </div>
    <div class="kpi neutral">
      <div class="label">今日检测总量</div>
      <div class="value" id="todayTotal">0</div>
      <div class="sub">桌面 + 扩展</div>
    </div>
    <div class="kpi total">
      <div class="label">累计高危拦截</div>
      <div class="value" id="totalHigh">0</div>
      <div class="sub">全部历史记录</div>
    </div>
  </div>

    <!-- 主图：7天趋势（大）+ 等级分布（小） -->
  <div class="row-main">
    <div class="card">
      <h3>检测趋势
        <span class="hint">
          <button class="range-btn" data-days="1">今天</button>
          <button class="range-btn active" data-days="7">7天</button>
          <button class="range-btn" data-days="30">30天</button>
        </span>
      </h3>
      <div id="trendChart" style="height: 300px;"></div>
    </div>
    <div class="card">
      <h3>等级分布 <span class="hint">累计</span></h3>
      <div id="levelPie" style="height: 300px;"></div>
    </div>
  </div>

  <!-- 副图：来源 + 热门域名 -->
  <div class="row-sub">
    <div class="card">
      <h3>上报来源 <span class="hint">桌面工具 vs 浏览器扩展</span></h3>
      <div id="sourcePie" style="height: 240px;"></div>
    </div>
    <div class="card">
      <h3>热门钓鱼域名 Top 10 <span class="hint">仅统计高危+可疑</span></h3>
      <div id="hostBar" style="height: 240px;"></div>
    </div>
  </div>

  </div>
  </div><!-- /tab-dashboard -->

  <!-- 检测记录 Tab -->
  <div class="tab-pane" id="tab-records">
  <!-- 表格 -->
  <div class="table-card">
    <div class="table-toolbar">
      <h3>检测记录</h3>
      <select id="filterSel">
        <option value="">全部等级</option>
        <option value="高危">高危</option>
        <option value="可疑">可疑</option>
        <option value="安全">安全</option>
        <option value="未知">未知</option>
      </select>
      <input type="text" id="searchInput" placeholder="搜索网站域名..." style="width:200px;">
      <div class="spacer"></div>
      <button onclick="location.href='/api/export.csv'">导出 CSV</button>
    </div>
    <table>
      <thead><tr><th>网站</th><th>等级</th><th>得分</th><th>来源</th><th>风险原因</th><th>时间</th></tr></thead>
      <tbody id="recentBody"></tbody>
    </table>
    <div class="pagination">
      <button id="prevPage">上一页</button>
      <span class="page-info" id="pageInfo">第 1 / 1 页</span>
      <button id="nextPage">下一页</button>
    </div>
  </div>
  </div><!-- /tab-records -->

  <!-- 告警管理 Tab：只看高危+可疑 -->
  <div class="tab-pane" id="tab-alerts">
    <div class="kpi-row" style="grid-template-columns:1fr 1fr;">
      <div class="kpi kpi-highlight">
        <div class="label">待处置高危</div>
        <div class="value" id="alertHigh">0</div>
        <div class="sub">累计全部高危记录</div>
      </div>
      <div class="kpi warn">
        <div class="label">待复核可疑</div>
        <div class="value" id="alertSusp">0</div>
        <div class="sub">累计全部可疑记录</div>
      </div>
    </div>
    <div class="table-card">
      <div class="table-toolbar">
        <h3>告警列表（仅高危 + 可疑）</h3>
        <div class="spacer"></div>
        <button onclick="location.href='/api/export.csv'">导出 CSV</button>
      </div>
      <table>
        <thead><tr><th>网站</th><th>等级</th><th>得分</th><th>来源</th><th>风险原因</th><th>时间</th></tr></thead>
        <tbody id="alertBody"></tbody>
      </table>
    </div>
  </div>

  <!-- 系统设置 Tab -->
  <div class="tab-pane" id="tab-settings">
    <div class="row-sub" style="grid-template-columns:1fr 1fr;">
      <div class="card">
        <h3>检测阈值 <span class="hint">当前生效</span></h3>
        <p style="font-size:14px;line-height:2;color:#374151;">
          <b style="color:#dc2626;">高危</b>：相似度 ≥ 66 分，立即拦截<br>
          <b style="color:#d97706;">可疑</b>：相似度 31–65 分，弹窗提醒<br>
          <b style="color:#16a34a;">安全</b>：相似度 ≤ 30 分，放行
        </p>
      </div>
      <div class="card">
        <h3>上报来源 <span class="hint">实时</span></h3>
        <p style="font-size:14px;line-height:2;color:#374151;">
          <b>桌面端</b>：校园钓鱼检测助手.exe，本地检测后上报<br>
          <b>浏览器扩展</b>：打开网页时 content script 自动检测
        </p>
      </div>
    </div>
    <div class="card">
      <h3>关于 <span class="hint">v2.3</span></h3>
      <p style="font-size:14px;line-height:2;color:#374151;">
        校园网盾 · 高校钓鱼网页轻量检测助手 v2.3<br>
        核心算法：Levenshtein 域名形近相似度 + 规则引擎 + 随机森林分类器<br>
        数据存储：本地 SQLite，所有记录不出校园网
      </p>
    </div>
  </div>
</div>

<script>
// XSS 防护：转义用户可控字段
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
let allRecent = [];
let currentDays = 7;
let currentPage = 1;
let totalPages = 1;
let currentFilter = "";
let currentSearch = "";
function renderTable() {
  const tbody = document.getElementById('recentBody');
  tbody.innerHTML = allRecent.map(r => {
    const lvl = r.level === '高危' ? 'level-high' : r.level === '可疑' ? 'level-susp' : r.level === '未知' ? 'level-unknown' : 'level-safe';
    const src = r.source === 'desktop' ? 'src-desktop' : 'src-ext';
    const srcName = r.source === 'desktop' ? '桌面' : '扩展';
    return `<tr>
      <td style="font-family:monospace;">${esc(r.host)}</td>
      <td><span class="level ${lvl}">${esc(r.level)}</span></td>
      <td>${esc(r.score)}</td>
      <td><span class="src ${src}"><span class="dot"></span>${srcName}</span></td>
      <td style="color:#6b7280;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(r.reason)}</td>
      <td style="color:#9ca3af;font-size:12px;">${esc(r.time)}</td>
    </tr>`;
  }).join('');
  document.getElementById('pageInfo').textContent = `第 ${currentPage} / ${totalPages} 页`;
  document.getElementById('prevPage').disabled = currentPage <= 1;
  document.getElementById('nextPage').disabled = currentPage >= totalPages;
}
document.getElementById('filterSel').addEventListener('change', e => { currentFilter = e.target.value; currentPage = 1; loadData(); });
document.getElementById('searchInput').addEventListener('input', e => { currentSearch = e.target.value.trim(); currentPage = 1; loadData(); });
document.getElementById('prevPage').addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadData(); } });
document.getElementById('nextPage').addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; loadData(); } });
document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentDays = parseInt(btn.dataset.days);
    loadData();
  });
});

// Tab 切换
document.querySelectorAll('.topbar nav a').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.topbar nav a').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById('tab-' + a.dataset.tab).classList.add('active');
    // 切到 tab 时重绘图表，避免尺寸 0
    setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
  });
});

// 时钟
function tick() {
  const d = new Date();
  document.getElementById('clock').textContent =
    d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') +
    ' ' + String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
}
tick(); setInterval(tick, 1000);

function loadData() {
  const params = new URLSearchParams({
    days: currentDays,
    page: currentPage,
    per_page: 20,
  });
  if (currentFilter) params.set('level', currentFilter);
  if (currentSearch) params.set('host', currentSearch);
  fetch('/api/stats?' + params.toString()).then(r => r.json()).then(data => {
    allRecent = data.recent;
    currentPage = data.page;
    totalPages = data.total_pages || 1;
    const ld = data.level_dist;
    // 今日数据
    const todayStr = new Date().toISOString().slice(0,10);
    const todayData = (data.daily.find(d => d.date === todayStr.slice(5)) || {});
    document.getElementById('todayHigh').textContent = todayData['高危'] || 0;
    document.getElementById('todaySusp').textContent = todayData['可疑'] || 0;
    document.getElementById('todayTotal').textContent = data.today_count;
    document.getElementById('totalHigh').textContent = ld['高危'] || 0;

    // 趋势图
    echarts.init(document.getElementById('trendChart')).setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['高危','可疑','安全','未知'], right: 0, top: 0 },
      grid: { left: 40, right: 20, top: 36, bottom: 30 },
      xAxis: { type: 'category', data: data.daily.map(d=>d.date), axisLine:{lineStyle:{color:'#e5e7eb'}}, axisTick:{show:false} },
      yAxis: { type: 'value', splitLine:{lineStyle:{color:'#f3f4f6'}} },
      series: [
        { name:'高危', type:'line', smooth:true, data:data.daily.map(d=>d['高危']||0), itemStyle:{color:'#dc2626'}, areaStyle:{color:'rgba(220,38,38,0.08)'} },
        { name:'可疑', type:'line', smooth:true, data:data.daily.map(d=>d['可疑']||0), itemStyle:{color:'#f59e0b'} },
        { name:'安全', type:'line', smooth:true, data:data.daily.map(d=>d['安全']||0), itemStyle:{color:'#16a34a'} },
        { name:'未知', type:'line', smooth:true, data:data.daily.map(d=>d['未知']||0), itemStyle:{color:'#d1d5db'} },
      ]
    });

    // 等级分布
    echarts.init(document.getElementById('levelPie')).setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie', radius: ['50%','75%'], center: ['50%','55%'],
        label: { fontSize: 12, formatter: '{b}: {c}' },
        data: [
          { value: ld['高危']||0, name:'高危', itemStyle:{color:'#dc2626'} },
          { value: ld['可疑']||0, name:'可疑', itemStyle:{color:'#f59e0b'} },
          { value: ld['安全']||0, name:'安全', itemStyle:{color:'#16a34a'} },
          { value: ld['未知']||0, name:'未知', itemStyle:{color:'#e5e7eb'} },
        ]
      }]
    });

    // 来源
    const sd = data.source_dist;
    echarts.init(document.getElementById('sourcePie')).setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [{
        type: 'pie', radius: ['40%','65%'], center: ['50%','45%'],
        label: { show: false },
        data: [
          { value: sd['desktop']||0, name:'桌面工具', itemStyle:{color:'#dc2626'} },
          { value: sd['extension']||0, name:'浏览器扩展', itemStyle:{color:'#3b82f6'} },
        ]
      }]
    });

    // 热门域名
    const hosts = data.top_hosts || [];
    echarts.init(document.getElementById('hostBar')).setOption({
      tooltip: {},
      grid: { left: 10, right: 20, top: 10, bottom: 10, containLabel: true },
      xAxis: { type: 'value', splitLine:{lineStyle:{color:'#f3f4f6'}} },
      yAxis: { type: 'category', data: hosts.map(h=>h.host).reverse(), axisLine:{show:false}, axisTick:{show:false} },
      series: [{ type: 'bar', data: hosts.map(h=>h.count).reverse(), itemStyle:{color:'#dc2626', borderRadius:[0,4,4,0]}, barWidth: 14 }]
    });

    renderTable();

    // 告警管理 tab
    document.getElementById('alertHigh').textContent = ld['高危'] || 0;
    document.getElementById('alertSusp').textContent = ld['可疑'] || 0;
    const alerts = allRecent.filter(r => r.level === '高危' || r.level === '可疑');
    document.getElementById('alertBody').innerHTML = alerts.length ? alerts.map(r => {
      const lvl = r.level === '高危' ? 'level-high' : 'level-susp';
      const src = r.source === 'desktop' ? 'src-desktop' : 'src-ext';
      const srcName = r.source === 'desktop' ? '桌面' : '扩展';
      return `<tr>
        <td style="font-family:monospace;">${esc(r.host)}</td>
        <td><span class="level ${lvl}">${esc(r.level)}</span></td>
        <td>${esc(r.score)}</td>
        <td><span class="src ${src}"><span class="dot"></span>${srcName}</span></td>
        <td style="color:#6b7280;">${esc(r.reason)}</td>
        <td style="color:#9ca3af;font-size:12px;">${esc(r.time)}</td>
      </tr>`;
    }).join('') : '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:40px;">暂无告警</td></tr>';
  });
}
loadData();
setInterval(loadData, 10000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  校园钓鱼检测后台已启动")
    print("  访问地址：http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False)
