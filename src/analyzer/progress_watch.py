"""
《春秋》分析进度 — CMD 实时监控窗口（自愈版）
双开一个 cmd 运行: python progress_watch.py
功能：实时显示进度 + 检测脚本停止 → 自动重启
"""
import json
import os
import time
import sys
import subprocess
from pathlib import Path

WORK_DIR = Path(__file__).parent.parent.parent  # 项目根目录
CHECKPOINT = WORK_DIR / "data/novel_analysis/checkpoints/chunk_analyses.json"
PHASE_FILE = WORK_DIR / "data/novel_analysis/phase_progress.json"
NOVEL_PATH = WORK_DIR / "data/chunqiu-txt/春秋人生之重合.txt"

# 自动加载 .env
ENV_FILE = Path(WORK_DIR) / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

PYTHON_EXE = r"D:\ProgramFiles\Python3.7\python.exe"

# 停顿时长阈值：检查点超过此时间未更新，判定脚本已死
STALL_SECONDS = 180  # 3 分钟

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def bar(done, total, width=40):
    pct = done / total if total else 0
    filled = int(width * pct)
    return "█" * filled + "░" * (width - filled)

def is_process_running() -> bool:
    """检查是否有 novel_analyzer.py 进程在运行"""
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', 'commandline like "%novel_analyzer.py%"', 'get', 'ProcessId'],
            capture_output=True, text=True, timeout=5
        )
        lines = [l.strip() for l in result.stdout.split('\n') if l.strip().isdigit()]
        return len(lines) > 0
    except:
        return False

def is_alive() -> tuple[bool, float]:
    """检查脚本是否还在运行（进程存在 或 检查点最近更新）"""
    # 如果有进程在跑，直接判定活着
    if is_process_running():
        return True, 0
    # 否则看检查点更新时间
    if not CHECKPOINT.exists():
        return False, 0
    mtime = os.path.getmtime(str(CHECKPOINT))
    stale = time.time() - mtime
    return stale < STALL_SECONDS, stale

def restart_script():
    """重新启动分析脚本（后台，无窗口，先杀旧进程）"""
    # 检查是否有可用的 API Key（至少一个）
    has_key = any(
        os.environ.get(k) for k in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY_1"]
    )
    if not has_key:
        print(f"\n  ❌ 未检测到任何 API Key，请检查 .env 文件")
        return False
    
    try:
        script_path = Path(WORK_DIR) / "src/analyzer/novel_analyzer.py"
        if not script_path.exists():
            print(f"\n  ❌ 找不到脚本: {script_path}")
            return False
        
        # 先杀掉所有旧的 novel_analyzer 进程
        subprocess.run(
            ['taskkill', '/F', '/IM', 'python.exe', '/FI', 'WINDOWTITLE eq novel_analyzer*'],
            capture_output=True, timeout=5
        )
        
        # 后台启动，用 shell=True 确保环境完整继承
        subprocess.Popen(
            f'python "{script_path}" "{NOVEL_PATH}"',
            cwd=WORK_DIR,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception as e:
        print(f"\n  ❌ 重启异常: {e}")
        return False

def main():
    print("\033[?25l", end="")
    
    last_done = 0
    start_time = time.time()
    restart_count = 0
    last_restart_time = 0
    
    try:
        while True:
            clear()
            
            # 读取进度
            done, total = 0, 1963
            valid = []
            
            if CHECKPOINT.exists():
                try:
                    with open(CHECKPOINT, "r", encoding="utf-8") as f:
                        cp = json.load(f)
                    results = cp.get("results", [])
                    valid = [r for r in results if r]
                    done = len(valid)
                    total = cp.get("total", 1963)
                except:
                    pass
            
            # ===== 检测脚本存活 =====
            alive, stale_secs = is_alive()
            status_text = ""
            
            if done >= total and done > 0:
                status_text = "✅ 已完成"
            elif done == 0:
                status_text = "⏳ 等待开始"
            elif alive:
                status_text = f"🟢 运行中"
            else:
                # 脚本已死，自动重启
                status_text = f"🔴 已停止 ({int(stale_secs)}秒)"
                
                # 冷却：避免频繁重启
                if time.time() - last_restart_time > 60:
                    print(f"\n  🔄 检测到脚本停止，正在自动重启...")
                    if restart_script():
                        restart_count += 1
                        last_restart_time = time.time()
                        print(f"  ✅ 已重启（共重启 {restart_count} 次）")
                    else:
                        print(f"  ❌ 重启失败！请手动运行: python novel_analyzer.py")
                    time.sleep(3)
                    continue
            
            # ===== 显示 =====
            pct = done / total * 100 if total else 0
            
            print("  ╔══════════════════════════════════════════════════════╗")
            print(f"  ║  📖 《春秋人生之重合》分析进度  {status_text}       ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print()
            
            print(f"  [{bar(done, total)}]")
            print(f"  {done:,} / {total:,}   ({pct:.1f}%)")
            print()
            
            # 速度 & ETA
            speed = 0
            if done > last_done:
                last_done = done
                start_time = time.time()
            
            if done > 10 and last_done > 0:
                elapsed = time.time() - start_time
                speed = max(0, done / (elapsed / 60) if elapsed > 30 else 0)
            
            if speed > 0:
                rem = total - done
                eta_min = int(rem / speed) if rem > 0 else 0
                h, m = divmod(eta_min, 60)
                eta_str = f"{h}时{m}分" if h else f"{m}分"
                print(f"  ⚡ 速度: {speed:.1f} 块/分钟  ⏱ 剩余: {eta_str}")
            else:
                print(f"  ⚡ 速度: 计算中...")
            print()
            
            # 当前
            if valid:
                last = valid[-1]
                ch = last.get("_source_title", "?")
                s = last.get("summary", "")[:60]
                print(f"  📍 当前: {ch}")
                print(f"      {s}...")
                print()
            
            # 阶段进度（Phase 3-5）
            if done >= total and total > 0:
                try:
                    with open(PHASE_FILE, "r", encoding="utf-8") as pf:
                        pp = json.load(pf)
                    phase_name = pp.get("phase", "")
                    phase_done = pp.get("done", 0)
                    phase_total = pp.get("total", 0)
                    phase_msg = pp.get("msg", "")
                    if phase_name and phase_total > 0:
                        phase_pct = phase_done / phase_total * 100
                        phase_bar = "▓" * int(phase_pct / 5) + "░" * (20 - int(phase_pct / 5))
                        print(f"  📊 {phase_name}: [{phase_bar}] {phase_done}/{phase_total} ({phase_pct:.0f}%)")
                        if phase_msg:
                            print(f"      {phase_msg}")
                        print()
                except:
                    pass
            
            # 最近 5 条
            print("  ── 最近完成 ──")
            for r in valid[-5:]:
                ch = r.get("_source_title", "")
                s = r.get("summary", "")[:32]
                print(f"  ✅ {ch[:25]:25s} {s}")
            print()
            
            # 完成
            if done >= total and total > 0:
                print("  🎉 全部分析完成！")
                print()
                print("  ╔══════════════════════════════════════════════════════╗")
                print("  ║  下一步: python build_framework.py                  ║")
                print("  ╚══════════════════════════════════════════════════════╝")
                print()
                print(f"  脚本共自动重启 {restart_count} 次")
                break
            
            if restart_count > 0:
                print(f"  🔧 自动重启: {restart_count} 次 | {time.strftime('%H:%M:%S')} | Ctrl+C 退出")
            else:
                print(f"  刷新于 {time.strftime('%H:%M:%S')} | Ctrl+C 退出")
            
            time.sleep(3)
            
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h", end="")

if __name__ == "__main__":
    main()
