"""
故事框架构建器 — 续作生成总控系统
=====================================
基于 novel_analyzer.py 的输出，构建：
  1. world_SOUL.md        — 世界观灵魂核心
  2. timeline_SOUL.md     — 时间线 + 关键转折点 + 未解伏笔
  3. story_framework.json — 续作生成总控文件
  4. character_map.json   — 角色关系图谱
  5. sequel_chapter_01.md — MV
P 第一章续作

用法：
  python build_framework.py [--chapter SUMMARY_FILE]

依赖：
  - novel_analyzer.py 的输出目录 output/novel_analysis/
  - DeepSeek API（仅用于生成续作第一章、合并世界观）
"""

import os
import re
import json
import sys
import time
from pathlib import Path
from openai import OpenAI

# ============================================================
# 配置
# ============================================================
INPUT_DIR = Path("data/novel_analysis")
CHARACTER_DIR = INPUT_DIR / "characters"
CHECKPOINT_DIR = INPUT_DIR / "checkpoints"
OUTPUT_DIR = Path("output/story_framework")

# ============================================================
# 工具
# ============================================================
def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def call_deepseek(system_prompt: str, user_prompt: str, max_tokens=4096) -> dict | None:
    # 支持编号 Key
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY_1", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not api_key:
        print("❌ 未设置 DEEPSEEK_API_KEY")
        return None
    
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0, max_retries=0)
    for attempt in range(3):
        try:
            time.sleep(1.0)
            resp = client.chat.completions.create(
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            print(f"  ⚠ API 失败 ({attempt+1}/3): {str(e)[:80]}")
            time.sleep(5)
    return None

# ============================================================
# 1. 世界观 SOUL.md
# ============================================================
def build_world_soul(chapter_summaries: list, stage_summaries: list):
    """构建世界观灵魂核心"""
    print("\n🌍 构建 world_SOUL.md...")
    
    # 从已有分析中提取世界观片段
    world_elements = []
    for ch in chapter_summaries:
        wb = ch.get("worldbuilding", [])
        if wb:
            world_elements.extend(wb)
    
    # 去重 + 合并同类
    seen = set()
    unique_wb = []
    for w in world_elements:
        key = w[:20]
        if key not in seen:
            seen.add(key)
            unique_wb.append(w)
    
    # 用 AI 结构化为文档
    world_md = f"""# 《春秋》世界观 — SOUL.md

> 自动构建于原著分析，供 AI 续作创作时作为世界规则约束参考

---

## 世界灵魂核心（用户定义）

> 世界的发展逻辑以人的想象力来引导。就如电影《寻梦环游记》的构想——当活在世界中的人没有人再记得你时，你才是真正的被遗忘，才会真正从这个世界消失。而以想象力构建的世界也是如此，当世界里一个想象出来的场景再也没有人提及或踏足时，也就该真正的消失了。数据保存下来也许是永恒的，但也有被抹除的一天。

---

## 世界结构

"""

    # 生成世界结构分析
    context = json.dumps({
        "world_elements": unique_wb[:50],
        "stage_summaries": [s.get("stage_summary", "") for s in (stage_summaries or [])[:5]],
    }, ensure_ascii=False)[:8000]

    system = """你是世界观架构师。基于小说《春秋》的分析数据，输出世界结构 JSON：
{
  "world_type": "世界类型（如：现实+虚拟游戏世界）",
  "core_mechanics": ["核心机制1", "核心机制2"],
  "power_system": "力量/能力体系描述",
  "major_factions": ["主要势力1", "主要势力2"],
  "geography": "世界地理概述",
  "rules": ["世界规则1", "世界规则2"],
  "forgetting_mechanism": "遗忘机制如何运作（寻梦环游记式）"
}
"""
    result = call_deepseek(system, context)
    
    if result:
        world_md += f"### 世界类型\n{result.get('world_type', '未知')}\n\n"
        world_md += f"### 核心机制\n" + "\n".join(f"- {m}" for m in result.get("core_mechanics", [])) + "\n\n"
        world_md += f"### 力量体系\n{result.get('power_system', '未知')}\n\n"
        world_md += f"### 主要势力\n" + "\n".join(f"- {f}" for f in result.get("major_factions", [])) + "\n\n"
        world_md += f"### 地理\n{result.get('geography', '未知')}\n\n"
        world_md += f"### 世界规则\n" + "\n".join(f"- {r}" for r in result.get("rules", [])) + "\n\n"
        world_md += f"### 遗忘机制\n{result.get('forgetting_mechanism', '未知')}\n\n"
    else:
        world_md += f"### 提取到的世界观元素\n" + "\n".join(f"- {w}" for w in unique_wb[:30]) + "\n\n"

    world_md += """## AI 创作约束

1. **不违反已建立的世界规则**：新章节中的任何能力、事件、设定必须与上述规则一致
2. **遗忘机制的体现**：每章至少有一处体现「记忆/遗忘」与「世界存续」的关系
3. **现实+虚拟双线**：注意区分现实世界（球场、学校）和游戏世界（梦想）的场景
4. **角色一致性**：参考各角色 SOUL.md，保持性格、说话风格不变

---

## 用户原始构想

> 世界很真实，也很魔幻，人的一生也不过如此。当世界变化的轨迹都是如你想象中的发展，每个人都交错在这样一个世界中，那该是多么的疯狂。

---

*基于原著 814 万字分析构建*
"""
    
    save_md(OUTPUT_DIR / "world_SOUL.md", world_md)
    print("  ✅ world_SOUL.md")
    return result


# ============================================================
# 2. 时间线 SOUL.md
# ============================================================
def build_timeline_soul(chapter_summaries: list, stage_summaries: list):
    """构建时间线 + 关键转折 + 未解伏笔"""
    print("\n📅 构建 timeline_SOUL.md...")
    
    # 汇总所有关键事件
    all_events = []
    last_chapters_raw = []  # 保存最后章节的完整摘要
    for i, ch in enumerate(chapter_summaries):
        events = ch.get("key_events", [])
        title = ch.get("_source_title", "")
        summary = ch.get("summary", "")
        if summary and "无正文内容" not in summary:
            all_events.append({
                "chapter": title,
                "events": events,
                "summary": summary[:200],
            })
            if i >= len(chapter_summaries) - 10:
                last_chapters_raw.append(f"【{title}】{summary}")
    
    # 构建上下文——重点强调结尾
    last_stages_text = "\n".join([s.get("stage_summary", "") for s in (stage_summaries or [])[-3:]])
    last_chapters_text = "\n".join(last_chapters_raw[-8:])
    
    context = json.dumps({
        "开头事件（前20章）": all_events[:20],
        "结尾章节完整摘要": last_chapters_text,
        "最后3个阶段总结": last_stages_text,
        "关键要求": "以上是小说《春秋》的完整内容。结尾章节在 第一百四十九章-第一百五十一章，描述了国战中的烈阳杀阵危机。current_state 和 sequel_starting_point 必须基于这些结尾章节，绝不能基于开头内容。",
    }, ensure_ascii=False)[:12000]
    
    system = """你是叙事分析师。基于小说《春秋》的事件数据，输出时间线分析 JSON：
{
  "timeline_overview": "整体时间线概述",
  "major_arcs": [{"name": "弧名", "chapters": "章节范围", "summary": "该弧摘要"}],
  "turning_points": [{"event": "关键事件", "impact": "对故事的影响"}],
  "unresolved_threads": [{"thread": "未解伏笔/线索", "last_mentioned": "最后出现章节", "importance": "高/中/低"}],
  "current_state": "故事截止点的状态描述（用于续作起点）",
  "sequel_starting_point": "续作从哪开始最自然、需要解释什么"
}
"""
    
    result = call_deepseek(system, context)
    
    timeline_md = """# 《春秋》时间线 — SOUL.md

> 自动构建于原著分析，供 AI 续作创作时维持时间线一致性

---

"""
    
    if result:
        timeline_md += f"## 时间线概述\n{result.get('timeline_overview', '未知')}\n\n"
        timeline_md += "## 主要故事弧\n\n"
        for arc in result.get("major_arcs", []):
            timeline_md += f"### {arc.get('name', '未知弧')}\n"
            timeline_md += f"- **章节范围**: {arc.get('chapters', '未知')}\n"
            timeline_md += f"- **摘要**: {arc.get('summary', '未知')}\n\n"
        
        timeline_md += "## 关键转折点\n\n"
        for tp in result.get("turning_points", []):
            timeline_md += f"- **{tp.get('event')}**: _{tp.get('impact')}_\n"
        
        timeline_md += "\n## ⚠ 未解伏笔（续作必须处理）\n\n"
        for ut in result.get("unresolved_threads", []):
            timeline_md += f"- **{ut.get('thread')}** (重要性: {ut.get('importance')}, 最后出现: {ut.get('last_mentioned')})\n"
        
        timeline_md += f"\n## 续作起点\n{result.get('sequel_starting_point', '未知')}\n\n"
        timeline_md += f"## 当前状态\n{result.get('current_state', '未知')}\n"
    else:
        timeline_md += "## 关键事件（自动提取）\n\n"
        for ev in all_events[:50]:
            timeline_md += f"### {ev['chapter']}\n{ev['summary']}\n"
            for e in ev.get('events', []):
                timeline_md += f"- {e}\n"
            timeline_md += "\n"
    
    save_md(OUTPUT_DIR / "timeline_SOUL.md", timeline_md)
    print("  ✅ timeline_SOUL.md")
    return result


# ============================================================
# 3. 角色关系图谱
# ============================================================
def build_character_map():
    """从角色 SOUL.md 和章节分析中构建关系图谱"""
    print("\n👥 构建 character_map.json...")
    
    if not CHARACTER_DIR.exists():
        print("  ⚠ characters/ 目录不存在，跳过")
        return None
    
    soul_files = list(CHARACTER_DIR.glob("*_SOUL.md"))
    characters = {}
    
    for sf in soul_files:
        name = sf.stem.replace("_SOUL", "")
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 提取关键信息
        traits = re.findall(r'- (.+)', content)
        relationships = {}
        
        # 尝试提取关系
        rel_section = re.search(r'## relationships\n\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if rel_section:
            rel_lines = rel_section.group(1).strip().split('\n')
            for line in rel_lines:
                m = re.match(r'- \*\*(.+?)\*\*: (.+)', line)
                if m:
                    relationships[m.group(1)] = m.group(2)
        
        characters[name] = {
            "file": str(sf),
            "traits": [t for t in traits if t and not t.startswith('*')][:5],
            "relationships": relationships,
        }
    
    # 构建双向关系图
    edges = []
    nodes = []
    for name, data in characters.items():
        nodes.append({"id": name, "traits": data["traits"]})
        for target, rel in data["relationships"].items():
            edges.append({"source": name, "target": target, "relationship": rel})
    
    char_map = {
        "nodes": nodes,
        "edges": edges,
        "total_characters": len(characters),
        "total_relationships": len(edges),
    }
    
    save_json(OUTPUT_DIR / "character_map.json", char_map)
    print(f"  ✅ character_map.json ({len(nodes)} 角色, {len(edges)} 关系)")
    return char_map


# ============================================================
# 4. 续作总控文件 story_framework.json
# ============================================================
def build_story_framework(world_data, timeline_data):
    """构建续作生成的万能 prompt 文件"""
    print("\n⚙️  构建 story_framework.json...")
    
    framework = {
        "meta": {
            "project": "《春秋》续作创作",
            "version": "1.0",
            "based_on": "原著 814 万字分析",
        },
        "world_constraints": {
            "rules": world_data.get("rules", []) if world_data else [],
            "core_mechanics": world_data.get("core_mechanics", []) if world_data else [],
            "forgetting_mechanism": world_data.get("forgetting_mechanism", "") if world_data else "",
        },
        "timeline": {
            "current_state": timeline_data.get("current_state", "") if timeline_data else "",
            "starting_point": timeline_data.get("sequel_starting_point", "") if timeline_data else "",
            "unresolved_threads": timeline_data.get("unresolved_threads", []) if timeline_data else [],
        },
        "character_reference": {
            "directory": str((INPUT_DIR / "characters_merged").absolute()),
            "fallback_directory": str(CHARACTER_DIR.absolute()),
        },
        "chapter_outline": {},
        "last_chapter_context": {
            "chapter_number": 0,
            "ending_summary": timeline_data.get("sequel_starting_point", "") if timeline_data else "",
            "character_states": {}
        },
        "generation_rules": {
            "chapter_length": "2000-5000 字/章",
            "style_guide": "保持原著叙事节奏和文风",
            "character_consistency": "参考各角色 SOUL.md，不改变已有性格特点",
            "world_consistency": "不违反 world_SOUL.md 中的任何规则",
            "timeline_consistency": "不产生时间线矛盾",
            "forgetting_mechanism_integration": "每章至少体现一次遗忘/记忆机制",
            "reader_feedback_integration": "后续章节将引入读者评论驱动机制（参考 story_framework.json 中的 feedback_loop 配置）",
        },
        "feedback_loop": {
            "enabled": False,
            "comment_sources": ["微信公众号", "B站评论", "抖音评论"],
            "analysis_prompt": "分析评论中的剧情偏好、角色好感度、情节走向建议",
            "integration_rule": "每收集 10 条有效评论后，生成一次方向调整建议",
        },
        "output_format": {
            "chapter_file": "sequel_chapter_{N:03d}.md",
            "include_metadata": True,
            "include_character_status": True,
            "include_reader_feedback_credit": True,
        },
    }
    
    save_json(OUTPUT_DIR / "story_framework.json", framework)
    print("  ✅ story_framework.json")
    return framework


# ============================================================
# 4.5. 生成章节大纲
# ============================================================
def build_chapter_outline(timeline_data, chapter_count=8):
    """基于未解伏笔生成章节大纲"""
    print("\n📋 构建章节大纲...")
    
    unresolved = json.dumps(timeline_data.get("unresolved_threads", []), ensure_ascii=False)
    current = timeline_data.get("current_state", "")
    
    prompt = f"""你是《春秋》续作的大纲策划。基于以下信息，规划 {chapter_count} 章大纲。

## 当前状态
{current}

## 未解伏笔
{unresolved}

## 要求
生成 {chapter_count} 章大纲 JSON：
{{
  "chapter_outline": [
    {{
      "chapter": 1,
      "title": "章节标题",
      "summary": "150字摘要",
      "key_scenes": ["场景"],
      "characters_involved": ["角色"],
      "threads_advanced": ["推进的伏笔"]
    }}
  ],
  "overall_arc": "整体故事弧线描述"
}}

注意：
1. 第1章内容应基于已经生成的 sequel_chapter_01.md
2. 每章必须至少推进1条伏笔
3. 遗忘机制至少在2章中出现
4. 诺诺的感情线在3章中体现
5. 到第{chapter_count}章时应有明显的故事推进"""
    
    result = call_deepseek("你是有经验的网文大纲策划师。", prompt)
    if result:
        outline = result.get("chapter_outline", [])
        overall = result.get("overall_arc", "")
        save_json(OUTPUT_DIR / "chapter_outline.json", result)
        print(f"  ✅ 章节大纲: {len(outline)} 章")
        return result
    else:
        print("  ⚠ 大纲生成失败")
        return None


# ============================================================
# 5. 生成续作第一章
# ============================================================
def generate_sequel_chapter_01(world_data, timeline_data, chapter_summaries=None):
    """基于世界规则 + 时间线当前状态 + 最后章节上下文，生成续作第一章"""
    print("\n✍️  生成 sequel_chapter_01.md...")
    
    # 读取人物 SOUL 文件（合并版优先）
    char_dir = INPUT_DIR / "characters_merged"
    if not char_dir.exists():
        char_dir = CHARACTER_DIR
    character_refs = ""
    if char_dir.exists():
        for sf in list(char_dir.glob("*_SOUL.md"))[:10]:
            name = sf.stem.replace("_SOUL", "")
            with open(sf, "r", encoding="utf-8") as f:
                content = f.read()[:400]
            character_refs += f"\n### {name}\n{content}\n"
    
    # 提取最后 5 章作为必须接续的上下文
    last_chapters_context = ""
    if chapter_summaries:
        meaningful = [c for c in chapter_summaries 
                      if c.get("summary") and "无正文内容" not in c.get("summary", "")]
        last_5 = meaningful[-5:]
        for c in last_5:
            title = c.get("_source_title", "")
            s = c.get("summary", "")[:200]
            events = c.get("key_events", [])[:3]
            last_chapters_context += f"- {title}: {s}\n"
            if events:
                last_chapters_context += f"  关键事件: {', '.join(events)}\n"
    
    starting_point = ""
    unresolved = ""
    current_state = ""
    world_rules = ""
    forgetting = ""
    
    if timeline_data:
        starting_point = timeline_data.get("sequel_starting_point", "")
        unresolved = json.dumps(timeline_data.get("unresolved_threads", []), ensure_ascii=False)
        current_state = timeline_data.get("current_state", "")
    
    if world_data:
        world_rules = json.dumps(world_data.get("rules", []), ensure_ascii=False)
        forgetting = world_data.get("forgetting_mechanism", "")
    
    prompt = f"""你是《春秋》的续作创作者。基于以下信息，写出续作第一章（2500-4000 字）。

## ⚠️ 最重要：第一章必须紧接原著最后一章
以下是原著最后几章的内容摘要，续作必须从这里开始写，不能跳到另一条时间线：

{last_chapters_context}

## 世界观约束
- 世界规则: {world_rules}
- 遗忘机制: {forgetting}

## 当前状态（基于原著结尾）
{current_state}

## 续作起点建议
{starting_point}

## 未解伏笔（需在第一章至少暗示其中1-2个）
{unresolved}

## 主要角色参考（含别名）
{character_refs[:3000]}

## 创作要求
1. 第一章必须作为原著最后一章的直接延续，从上一章结尾处接着写
2. 要作为「钩子」——让老读者立刻回到那个世界
3. 在叙事中自然体现「遗忘机制」
4. 必须出现诺诺（天寒的女友），可以描写两人的关系互动
5. 埋下 1-2 个伏笔供后续展开
6. 保持原著文风——现实和游戏两条线并行叙事
7. 结尾留悬念

请直接输出续作第一章正文（不要 JSON，纯叙事文本）。
"""

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY_1", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    if not api_key:
        print("  ❌ 未设置 DEEPSEEK_API_KEY，跳过第一章生成")
        return None
    
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0, max_retries=0)
    
    try:
        time.sleep(1.0)
        resp = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            messages=[
                {"role": "system", "content": f"你是一位资深网文创作者，擅长基于已有世界观创作高质量续作。你正在为小说《春秋》写续作第一章。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8192,
            temperature=0.7,
        )
        chapter_text = resp.choices[0].message.content
        
        # 写入文件
        chapter_md = f"""# 《春秋》续作 — 第一章

> 基于原著 814 万字全本分析 + 世界观约束生成
> 创作约束: 遗忘机制、现实+虚拟双线、角色一致性

---

{chapter_text}

---

*本章由 DeepSeek AI 基于《春秋》全本分析生成，作为 MVP 交付物*
"""
        save_md(OUTPUT_DIR / "sequel_chapter_01.md", chapter_md)
        print(f"  ✅ sequel_chapter_01.md ({len(chapter_text)} 字)")
        return chapter_text
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        return None


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("📦 故事框架构建器")
    print("=" * 60)
    
    # 自动加载 .env
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    
    # 检查 Key（兼容单一 KEY 和编号 KEY_1）
    has_key = any(os.environ.get(k) for k in ["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY_1"])
    if not has_key:
        print("❌ 未找到 API Key，请检查 .env")
        sys.exit(1)
    
    # 读取输入
    chapter_file = INPUT_DIR / "chapter_summaries.json"
    stage_file = INPUT_DIR / "stage_summaries.json"
    
    if not chapter_file.exists():
        print(f"❌ 找不到 {chapter_file}，请先运行 novel_analyzer.py")
        sys.exit(1)
    
    print(f"📖 加载章节摘要...")
    chapter_summaries = load_json(chapter_file)
    print(f"   {len(chapter_summaries)} 章节")
    
    stage_summaries = None
    if stage_file.exists():
        stage_summaries = load_json(stage_file)
        print(f"   {len(stage_summaries)} 阶段")
    
    # Step 1: 世界观
    world_data = build_world_soul(chapter_summaries, stage_summaries)
    
    # Step 2: 时间线
    timeline_data = build_timeline_soul(chapter_summaries, stage_summaries)
    
    # Step 3: 角色图谱
    char_map = build_character_map()
    
    # Step 4: 总控文件
    framework = build_story_framework(world_data, timeline_data)
    
    # Step 4.5: 章节大纲
    outline = build_chapter_outline(timeline_data)
    if outline:
        framework["chapter_outline"] = outline
    
    # Step 5: 续作第一章
    chapter_01 = generate_sequel_chapter_01(world_data, timeline_data, chapter_summaries)
    
    print(f"\n{'='*60}")
    print(f"✅ 构建完成！")
    print(f"{'='*60}")
    print(f"\n📁 输出: {OUTPUT_DIR.absolute()}")
    print(f"   ├── world_SOUL.md           世界观灵魂核心")
    print(f"   ├── timeline_SOUL.md        时间线 + 未解伏笔")
    print(f"   ├── chapter_outline.json    章节大纲")
    print(f"   ├── character_map.json      角色关系图谱")
    print(f"   ├── story_framework.json    续作生成总控文件")
    print(f"   └── sequel_chapter_01.md    MVP 第一章续作")


if __name__ == "__main__":
    main()
