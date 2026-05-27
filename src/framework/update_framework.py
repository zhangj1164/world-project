"""
框架状态更新器
==============
写完一章后，更新 story_framework.json 的 current_state。
保持故事连贯性——每章结尾就是下一章的起点。

用法：
  python update_framework.py sequel_chapter_01.md    # 更新到第1章结尾
  python update_framework.py sequel_chapter_02.md    # 累积更新
"""
import json
import os
import sys
from pathlib import Path
from openai import OpenAI

FRAMEWORK_FILE = Path("output/story_framework/story_framework.json")
STORY_DIR = Path("output/story_framework")

def load_env():
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

def call_deepseek(system: str, prompt: str) -> dict | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY_1", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    if not api_key:
        print("❌ 未设置 API Key")
        return None
    
    for attempt in range(3):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=180, max_retries=0)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            import time
            print(f"  ⚠ API 失败 ({attempt+1}/3): {str(e)[:50]}")
            time.sleep(5 * (attempt + 1))
    return None


def main():
    load_env()
    import time
    
    if len(sys.argv) < 2:
        print("用法: python update_framework.py <章节文件>")
        print("示例: python update_framework.py sequel_chapter_01.md")
        sys.exit(1)
    
    chapter_path = Path(sys.argv[1])
    if not chapter_path.exists():
        # 尝试在 STORY_DIR 中查找
        chapter_path = STORY_DIR / sys.argv[1]
    if not chapter_path.exists():
        print(f"❌ 找不到文件: {chapter_path}")
        sys.exit(1)
    
    print("=" * 60)
    print(f"🔄 更新故事框架 — {chapter_path.name}")
    print("=" * 60)
    
    # 1. 读取当前框架
    with open(FRAMEWORK_FILE, "r", encoding="utf-8") as f:
        framework = json.load(f)
    
    # 2. 读取章节内容
    with open(chapter_path, "r", encoding="utf-8") as f:
        chapter_text = f.read()
    
    # 提取章节号和标题
    lines = chapter_text.strip().split("\n")
    chapter_title = "第一章"
    for line in lines[:5]:
        if line.startswith("# "):
            chapter_title = line.replace("# ", "").strip()
            break
    
    # 取章节最后 2000 字符作为结尾上下文
    ending_text = chapter_text[-2000:]
    
    # 3. AI 分析新状态
    old_state = framework["timeline"]["current_state"]
    old_threads = json.dumps(framework["timeline"]["unresolved_threads"], ensure_ascii=False)
    
    prompt = f"""你是《春秋》续作的框架维护者。上一章已写完，请分析章节结尾，更新故事状态。

## 前一章状态
{old_state}

## 本章内容结尾
{ending_text}

## 已有伏笔
{old_threads}

## 输出 JSON
{{
  "new_current_state": "本章结尾的世界状态（150字内，用于下一章续写）",
  "resolved_threads": ["已解决的伏笔"],
  "new_threads": [{{"thread": "新伏笔", "last_mentioned": "当前章节", "importance": "高/中/低"}}],
  "chapter_history_update": "章节摘要（50字）"
}}
"""
    
    result = call_deepseek("你是严格的故事状态跟踪器。只分析章节末尾的客观状态。", prompt)
    
    if not result:
        print("❌ AI 分析失败，框架未更新")
        sys.exit(1)
    
    # 4. 更新框架
    # 更新 current_state
    new_state = result.get("new_current_state", "")
    if new_state:
        framework["timeline"]["current_state"] = new_state
        print(f"\n✅ current_state 已更新")
        print(f"   旧: {old_state[:60]}...")
        print(f"   新: {new_state[:60]}...")
    
    # 更新 resolved_threads
    resolved = result.get("resolved_threads", [])
    if resolved:
        threads = framework["timeline"]["unresolved_threads"]
        kept = [t for t in threads if t.get("thread") not in resolved]
        framework["timeline"]["unresolved_threads"] = kept
        print(f"✅ 已解决 {len(resolved)} 条伏笔")
    
    # 添加新伏笔
    new_threads = result.get("new_threads", [])
    if new_threads:
        framework["timeline"]["unresolved_threads"].extend(new_threads)
        print(f"✅ 新伏笔: {len(new_threads)} 条")
    
    # 更新 last_chapter_context
    ch_num = len(framework.get("last_chapter_context", {}).get("chapter_history", [])) + 1
    if "last_chapter_context" not in framework:
        framework["last_chapter_context"] = {}
    framework["last_chapter_context"]["chapter_number"] = ch_num
    framework["last_chapter_context"]["ending_summary"] = result.get("chapter_history_update", "")
    
    # 时间戳
    framework["meta"]["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    # 5. 保存
    with open(FRAMEWORK_FILE, "w", encoding="utf-8") as f:
        json.dump(framework, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ 框架已更新: {FRAMEWORK_FILE}")
    print(f"   当前章节: {chapter_title}")
    print(f"   待解决伏笔: {len(framework['timeline']['unresolved_threads'])} 条")
    print(f"   下次生成时请重新运行 build_framework.py 或直接使用当前 framework")


if __name__ == "__main__":
    main()
