"""快速生成章节大纲（独立运行，不受 build_framework 卡顿影响）"""
import json, os, sys, time
from pathlib import Path
from openai import OpenAI

FRAMEWORK_FILE = Path("output/story_framework/story_framework.json")
OUTLINE_FILE = Path("output/story_framework/chapter_outline.json")

def load_env():
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

def main():
    load_env()
    
    with open(FRAMEWORK_FILE, "r", encoding="utf-8") as f:
        framework = json.load(f)
    
    tl = framework["timeline"]
    current_state = tl["current_state"]
    threads = json.dumps(tl["unresolved_threads"], ensure_ascii=False)
    
    api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY_1", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    
    prompt = f"""规划《春秋》续作 8 章大纲。大纲要体现故事推进，每章有明确场景和角色。

当前状态: {current_state}
未解伏笔: {threads}

输出 JSON：{{"chapter_outline": [{{"chapter": 1, "title": "标题", "summary": "100字", "key_scenes": ["场景"], "characters_involved": ["角色"], "threads_advanced": ["推进的伏笔"]}}], "overall_arc": "整体弧线"}}

规则：第1章已写成「阵破」（天寒破烈阳杀阵），从第2章规划；诺诺感情线至少3章；遗忘机制至少2章；到第8章有明显阶段收束。"""
    
    print("📋 生成章节大纲...")
    for attempt in range(3):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=120)
            resp = client.chat.completions.create(
                model=model, messages=[
                    {"role": "system", "content": "你是网文大纲策划师。"},
                    {"role": "user", "content": prompt},
                ], max_tokens=4096, temperature=0.5,
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            
            with open(OUTLINE_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            outline = result.get("chapter_outline", [])
            print(f"✅ 大纲已生成: {len(outline)} 章")
            for ch in outline:
                print(f"  第{ch['chapter']}章 {ch['title']}")
            print(f"\n整体弧线: {result.get('overall_arc', '')}")
            
            # 更新 framework
            framework["chapter_outline"] = result
            with open(FRAMEWORK_FILE, "w", encoding="utf-8") as f:
                json.dump(framework, f, ensure_ascii=False, indent=2)
            return
        except Exception as e:
            print(f"  ⚠ 尝试 {attempt+1} 失败: {str(e)[:60]}")
            time.sleep(5)
    
    print("❌ 大纲生成失败")

if __name__ == "__main__":
    main()
