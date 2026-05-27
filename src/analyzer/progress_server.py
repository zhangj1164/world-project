"""
小说分析进度面板 HTTP 服务
启动后访问 http://localhost:8899 查看实时进度
"""

import http.server
import json
import os
import time
import threading
from pathlib import Path

CHECKPOINT_PATH = Path("F:/Personal/world-project/output/novel_analysis/checkpoints/chunk_analyses.json")
PROGRESS_LOG = Path("F:/Personal/world-project/output/novel_analysis/progress.log")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📖 《春秋》分析进度面板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: #0f0f1a;
    color: #e0e0e0;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; padding: 20px;
  }
  .panel {
    background: #1a1a2e; border: 1px solid #2a2a4a;
    border-radius: 16px; padding: 32px;
    max-width: 620px; width: 100%;
    box-shadow: 0 0 60px rgba(100,100,255,0.08);
  }
  .title {
    font-size: 22px; font-weight: 700; margin-bottom: 6px;
    display: flex; align-items: center; gap: 10px;
  }
  .subtitle { color: #888; font-size: 13px; margin-bottom: 24px; }
  
  .progress-bar-outer {
    height: 32px; background: #12122a; border-radius: 16px;
    overflow: hidden; margin-bottom: 16px;
    border: 1px solid #2a2a4a;
  }
  .progress-bar-inner {
    height: 100%; border-radius: 16px;
    background: linear-gradient(90deg, #4F6EF7, #7B93FF);
    transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex; align-items: center; justify-content: flex-end;
    padding-right: 14px; font-size: 13px; font-weight: 600;
    min-width: 50px; color: #fff;
  }
  
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
  .stat-card {
    background: #12122a; border: 1px solid #2a2a4a;
    border-radius: 10px; padding: 14px; text-align: center;
  }
  .stat-value { font-size: 28px; font-weight: 700; color: #7B93FF; }
  .stat-label { font-size: 12px; color: #888; margin-top: 4px; }
  
  .log-box {
    background: #0a0a16; border: 1px solid #1a1a3a;
    border-radius: 10px; padding: 14px; height: 200px;
    overflow-y: auto; font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px; color: #aaa; line-height: 1.6;
  }
  .log-box .chapter { color: #7B93FF; }
  .log-box .success { color: #4ade80; }
  
  .status-dot {
    display: inline-block; width: 10px; height: 10px;
    border-radius: 50%; margin-right: 6px;
    animation: pulse 2s infinite;
  }
  .status-dot.running { background: #4ade80; }
  .status-dot.stopped { background: #f87171; }
  @keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
  }
  
  .footer { text-align: center; color: #555; font-size: 11px; margin-top: 16px; }
</style>
</head>
<body>
<div class="panel">
  <div class="title">
    <span class="status-dot" id="statusDot"></span>
    📖 《春秋人生之重合》分析进度
  </div>
  <div class="subtitle" id="subtitle">加载中...</div>
  
  <div class="progress-bar-outer">
    <div class="progress-bar-inner" id="progressBar">0%</div>
  </div>
  
  <div class="stats">
    <div class="stat-card">
      <div class="stat-value" id="statDone">--</div>
      <div class="stat-label">已完成</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" id="statTotal">--</div>
      <div class="stat-label">总块数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" id="statSpeed">--</div>
      <div class="stat-label">速度 (块/分钟)</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" id="statETA">--</div>
      <div class="stat-label">预估剩余</div>
    </div>
  </div>
  
  <div class="log-box" id="logBox">等待数据...</div>
  
  <div class="footer">每 3 分钟自动刷新 | 数据来源: checkpoint</div>
</div>

<script>
async function fetchProgress() {
  try {
    const resp = await fetch('/api/progress');
    const data = await resp.json();
    
    const pct = data.total > 0 ? (data.done / data.total * 100) : 0;
    
    document.getElementById('progressBar').style.width = pct + '%';
    document.getElementById('progressBar').textContent = pct.toFixed(1) + '%';
    
    document.getElementById('statDone').textContent = data.done;
    document.getElementById('statTotal').textContent = data.total;
    document.getElementById('statSpeed').textContent = data.speed;
    document.getElementById('statETA').textContent = data.eta;
    
    const dot = document.getElementById('statusDot');
    dot.className = 'status-dot ' + (data.status === 'running' ? 'running' : 'stopped');
    
    document.getElementById('subtitle').textContent = 
      data.total > 0 
        ? `最新章节: ${data.last_chapter || '--'} | 成功率: ${data.success_rate}%`
        : '等待分析开始...';
    
    // 日志
    if (data.log_lines && data.log_lines.length > 0) {
      document.getElementById('logBox').innerHTML = data.log_lines
        .map(l => {
          if (l.includes('✅')) return `<span class="success">${l}</span>`;
          if (l.includes('第') || l.includes('ch')) return `<span class="chapter">${l}</span>`;
          return l;
        })
        .join('<br>');
    }
  } catch(e) {
    document.getElementById('subtitle').textContent = '连接服务器中...';
  }
}

fetchProgress();
setInterval(fetchProgress, 180000);
</script>
</body>
</html>"""


class ProgressHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/progress":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            data = {
                "done": 0, "total": 1963, "pct": 0,
                "speed": "--", "eta": "--",
                "status": "stopped", "success_rate": 100,
                "last_chapter": "--", "log_lines": []
            }
            
            if CHECKPOINT_PATH.exists():
                try:
                    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                        cp = json.load(f)
                    results = cp.get("results", [])
                    valid = [r for r in results if r]
                    done = len(valid)
                    total = cp.get("total", 1963)
                    data["done"] = done
                    data["total"] = total
                    data["pct"] = round(done / total * 100, 1) if total else 0
                    data["success_rate"] = round(done / max(len(results), 1) * 100, 1)
                    data["status"] = "running" if done < total else "completed"
                    
                    # 最新章节
                    if valid:
                        last = valid[-1]
                        data["last_chapter"] = last.get("_source_title", "--")
                    
                    # 最近 20 行日志
                    log_lines = []
                    for i, r in enumerate(valid[-20:]):
                        title = r.get("_source_title", "?")
                        summary = r.get("summary", "")[:40]
                        cid = r.get("_chunk_id", "")
                        log_lines.append(f"[{cid}] {title} ✅ {summary}...")
                    data["log_lines"] = log_lines
                    
                    # 速度估算
                    from datetime import datetime
                    mtime = os.path.getmtime(str(CHECKPOINT_PATH))
                    elapsed = time.time() - mtime
                    if elapsed > 60 and done > 10:
                        spd = round(done / (elapsed / 60), 1)
                        rem = total - done
                        eta_min = int(rem / spd) if spd > 0 else 0
                        h, m = divmod(eta_min, 60)
                        data["speed"] = f"{spd}"
                        data["eta"] = f"{h}h {m}m" if h > 0 else f"{m}m"
                    else:
                        data["speed"] = "计算中..."
                        data["eta"] = "计算中..."
                        
                except Exception as e:
                    data["log_lines"] = [f"读取失败: {e}"]
            
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return
        
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return
        
        super().do_GET()


def main():
    port = 8899
    server = http.server.HTTPServer(("0.0.0.0", port), ProgressHandler)
    print(f"📊 进度面板已启动: http://localhost:{port}")
    print(f"   按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ 服务已停止")


if __name__ == "__main__":
    main()
