"""
故事续写 Agent
==============
流水线式生成续作章节，支持未来接入多种输入源。

模式：
  # 标准模式（生成下一章）
  python story_pipeline.py

  # 指定章节号
  python story_pipeline.py 2

  # 带用户反馈生成
  python story_pipeline.py --feedback "角色A的戏份太少了"

  # 读者评论驱动（未来）
  python story_pipeline.py --comments comments.json

流水线阶段：
  1. 加载框架状态
  2. 收集外部输入（反馈/评论/分析）
  3. 构建上下文（框架 + 前章 + 输入）
  4. AI 生成章节
  5. 自动更新框架状态
  6. 输出章节文件
"""
import json
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# ============================================================
# 配置
# ============================================================
WORK_DIR = Path(__file__).parent.parent.parent  # 项目根目录
FRAMEWORK_FILE = WORK_DIR / "output/story_framework/story_framework.json"
STORY_DIR = WORK_DIR / "output/story_framework"
CHAR_DIR = WORK_DIR / "data/novel_analysis/characters_merged"
CHAR_FALLBACK = WORK_DIR / "data/novel_analysis/characters"
RELATIONSHIP_FILE = WORK_DIR / "output/story_framework/character_relationships.json"


def load_env():
    env_file = WORK_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


# ============================================================
# Pipeline 阶段
# ============================================================

class StoryPipeline:
    def __init__(self):
        load_env()
        self.framework = None
        self.char_context = ""
        self.feedback = []
        self.comments = []
        self.log = []  # 操作日志
    
    # ── 阶段 1：加载框架 ──
    def load_framework(self) -> dict:
        """加载故事框架和状态"""
        print("📖 [1/5] 加载框架...")
        with open(FRAMEWORK_FILE, "r", encoding="utf-8") as f:
            self.framework = json.load(f)
        
        tl = self.framework["timeline"]
        outline = self.framework.get("chapter_outline", {})
        threads = len(tl.get("unresolved_threads", []))
        outline_chs = len(outline.get("chapter_outline", []))
        
        print(f"   状态: {tl['current_state'][:60]}...")
        print(f"   大纲: {outline_chs} 章 | 伏笔: {threads} 条")
        return self.framework
    
    # ── 阶段 2：收集输入 ──
    def collect_inputs(self, feedback=None, comments_file=None):
        """收集外部输入（可扩展）"""
        print("📥 [2/5] 收集输入...")
        
        # 2a. 用户反馈
        if feedback:
            self.feedback.append({
                "time": datetime.now().isoformat(),
                "source": "user",
                "content": feedback,
            })
            print(f"   💬 用户反馈: {feedback[:60]}")
        
        # 2b. 读者评论（未来接入）
        if comments_file:
            cp = Path(comments_file)
            if cp.exists():
                with open(cp, "r", encoding="utf-8") as f:
                    self.comments = json.load(f)
                print(f"   📊 读者评论: {len(self.comments)} 条")
        
        # 2c. 角色上下文（加载合并版 SOUL）
        char_dir = CHAR_DIR if CHAR_DIR.exists() else CHAR_FALLBACK
        soul_files = list(char_dir.glob("*_SOUL.md"))
        if len(soul_files) > 20:
            # 只取核心角色
            import random
            core_names = {"天寒", "独孤天寒", "肥鸭", "陆易", "诺诺", "阿紫", 
                         "紫垣旋忆", "小猪", "小雪", "绯雨", "幽心", "幽雨",
                         "小龙", "宝宝", "快刀浪子", "石大夫", "文言", "鲁将军"}
            selected = [s for s in soul_files if s.stem.replace("_SOUL", "") in core_names]
        else:
            selected = soul_files
        
        self.char_context = ""
        for sf in selected[:10]:
            name = sf.stem.replace("_SOUL", "")
            with open(sf, "r", encoding="utf-8") as f:
                content = f.read()[:300]
            self.char_context += f"\n### {name}\n{content}\n"
        
        print(f"   👥 角色参考: {len(selected)} 个")
        return {
            "feedback": self.feedback,
            "comments": self.comments,
            "characters": len(selected),
        }
    
    # ── 阶段 3：构建提示 ──
    def build_prompt(self, chapter_num: int) -> str:
        """构建章节生成的完整 prompt"""
        print(f"🔧 [3/5] 构建第{chapter_num}章提示...")
        
        fw = self.framework
        tl = fw["timeline"]
        wc = fw["world_constraints"]
        
        # 大纲中当前章节的规划
        outline = fw.get("chapter_outline", {})
        chapter_plan = ""
        for ch in outline.get("chapter_outline", []):
            if ch.get("chapter") == chapter_num:
                chapter_plan = json.dumps(ch, ensure_ascii=False)
                break
        
        # 加载关系图谱（称呼约定）
        address_rules = ""
        if RELATIONSHIP_FILE.exists():
            with open(RELATIONSHIP_FILE, "r", encoding="utf-8") as f:
                rel_graph = json.load(f)
            address_book = rel_graph.get("address_book", {})
            # 只取核心角色称呼规则
            address_lines = []
            for name, data in address_book.items():
                calls = []
                for who, info in data.get("called_by", {}).items():
                    calls.append(f"{who}→{name}: \"{info['term']}\"")
                if calls:
                    address_lines.append(f"- {name}: {', '.join(calls[:5])}")
            address_rules = "称呼规则：\n" + "\n".join(address_lines[:10])
            address_rules += "\n- 每个角色只能使用约定的称呼，不得自行创造新称呼"
        
        if RELATIONSHIP_FILE.exists():
            ...
        lc = fw.get("last_chapter_context", {})
        last_summary = lc.get("ending_summary", "未知")
        
        # 用户反馈
        feedback_text = ""
        if self.feedback:
            recent = [f["content"] for f in self.feedback[-3:]]
            feedback_text = "\n".join(f"- {r}" for r in recent)
        
        # 读者评论
        comments_text = ""
        if self.comments:
            comment_topics = [c.get("topic", c.get("content", ""))[:60] for c in self.comments[-10:]]
            comments_text = "\n".join(f"- {t}" for t in comment_topics)
        
        prompt = f"""你是《春秋》续作的专业创作者。生成第 {chapter_num} 章。

## ⚠️ 核心约束
1. 必须紧接上一章结尾，不能跳跃时间线
2. 保持原著文风：现实+游戏双线叙事
3. 不改变任何角色的性格

## 世界观
规则: {json.dumps(wc.get('rules', []), ensure_ascii=False)}
遗忘机制: {wc.get('forgetting_mechanism', '')}

## 当前故事状态
{fw['timeline']['current_state']}

## 上一章结尾
{last_summary}

## 本章大纲规划
{chapter_plan if chapter_plan else '自由发挥，推进故事'}

## 角色参考
{self.char_context[:2000]}

## ⚠️ 称呼约定（严格遵守）
{address_rules if address_rules else '无特殊约定'}

## 外部输入
{'' if not feedback_text else f'用户反馈: {feedback_text}'}
{'' if not comments_text else f'读者评论倾向: {comments_text}'}

## 创作要求
- 2500-4000 字
- 每章至少体现一次遗忘/记忆机制
- 结尾留钩子
- 严格遵守上述称呼约定，每个角色对话时必须使用正确称呼
- {'若有用户反馈，在合理范围内采纳' if feedback_text else ''}
- {'参考读者评论倾向调整内容侧重' if comments_text else ''}

直接输出章节正文（纯文本），以「# 第{chapter_num}章 标题」开头。
"""
        return prompt
    
    # ── 阶段 4：AI 生成 ──
    def generate_chapter(self, chapter_num: int) -> str | None:
        """调用 AI 生成章节"""
        print(f"✍️ [4/5] 生成第{chapter_num}章...")
        
        prompt = self.build_prompt(chapter_num)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY_1", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        
        for attempt in range(3):
            try:
                client = OpenAI(api_key=api_key, base_url=base_url, timeout=300)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是专业网文创作者。"},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=8192,
                    temperature=0.7,
                )
                chapter_text = resp.choices[0].message.content
                
                # 保存章节
                chapter_file = STORY_DIR / f"sequel_chapter_{chapter_num:03d}.md"
                with open(chapter_file, "w", encoding="utf-8") as f:
                    f.write(chapter_text)
                
                word_count = len(chapter_text)
                print(f"   ✅ 已保存: {chapter_file.name} ({word_count} 字)")
                return chapter_text
            except Exception as e:
                print(f"   ⚠ 尝试 {attempt+1}/3: {str(e)[:60]}")
                time.sleep(5 * (attempt + 1))
        
        print("   ❌ 生成失败")
        return None
    
    # ── 阶段 5：更新框架 ──
    def update_state(self, chapter_num: int, chapter_text: str):
        """AI 分析章节结尾，更新框架状态"""
        print(f"🔄 [5/5] 更新框架状态...")
        
        api_key = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY_1", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        
        # 只用结尾 1500 字进行分析
        ending = chapter_text[-1500:]
        old_state = self.framework["timeline"]["current_state"]
        threads = json.dumps(self.framework["timeline"]["unresolved_threads"], ensure_ascii=False)
        
        prompt = f"""分析章节结尾，更新续作状态。

前一章状态: {old_state}
章节结尾: {ending}
已有伏笔: {threads}

输出 JSON:
{{
  "new_current_state": "150字状态描述（必须是本章结尾的状态，用于下一章）",
  "resolved_threads": ["已解决"],
  "new_threads": [{{"thread": "...", "importance": "高/中/低"}}],
  "chapter_summary": "50字章节摘要"
}}
"""
        
        for attempt in range(2):
            try:
                client = OpenAI(api_key=api_key, base_url=base_url, timeout=120)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "更新故事框架状态。只输出JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024, temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result = json.loads(resp.choices[0].message.content)
                
                # 更新 framework
                new_state = result.get("new_current_state", "")
                if new_state:
                    self.framework["timeline"]["current_state"] = new_state
                    print(f"   ✅ 状态更新: {new_state[:60]}...")
                
                # 处理伏笔
                resolved = result.get("resolved_threads", [])
                threads = self.framework["timeline"]["unresolved_threads"]
                self.framework["timeline"]["unresolved_threads"] = [
                    t for t in threads if t.get("thread") not in resolved
                ]
                
                new_threads = result.get("new_threads", [])
                self.framework["timeline"]["unresolved_threads"].extend(new_threads)
                
                # 更新章节上下文
                self.framework["last_chapter_context"] = {
                    "chapter_number": chapter_num,
                    "ending_summary": result.get("chapter_summary", ""),
                    "word_count": len(chapter_text),
                }
                
                # 更新元数据
                self.framework["meta"]["last_updated"] = datetime.now().isoformat()
                if "chapter_count" not in self.framework["meta"]:
                    self.framework["meta"]["chapter_count"] = 1
                else:
                    self.framework["meta"]["chapter_count"] = chapter_num
                
                # 保存
                with open(FRAMEWORK_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.framework, f, ensure_ascii=False, indent=2)
                
                print(f"   伏笔: {len(self.framework['timeline']['unresolved_threads'])} 条 | "
                      f"解决: {len(resolved)} | 新增: {len(new_threads)}")
                return result
                
            except Exception as e:
                print(f"   ⚠ 状态更新失败 ({attempt+1}/2): {str(e)[:60]}")
                time.sleep(3)
        
        print("   ⚠ 框架状态未自动更新，请手动运行 update_framework.py")
        return None
    
    # ── 流水线入口 ──
    def run(self, chapter_num=None, feedback=None, comments_file=None):
        """运行完整流水线"""
        print("=" * 60)
        print("🚀 故事续写流水线")
        print("=" * 60)
        
        # 确定章节号
        if chapter_num is None:
            fw = self.load_framework()
            chapter_num = fw["meta"].get("chapter_count", 1) + 1
        else:
            self.load_framework()
        
        print(f"\n📝 目标: 第 {chapter_num} 章")
        print(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # 阶段 2: 收集输入
        self.collect_inputs(feedback, comments_file)
        
        # 阶段 3+4: 生成
        chapter_text = self.generate_chapter(chapter_num)
        if not chapter_text:
            print("❌ 流水线中断")
            return None
        
        # 阶段 5: 更新状态
        self.update_state(chapter_num, chapter_text)
        
        # 摘要
        print(f"\n{'='*60}")
        print(f"✅ 第 {chapter_num} 章完成")
        print(f"   文件: sequel_chapter_{chapter_num:03d}.md")
        print(f"   字数: {len(chapter_text)}")
        print(f"   框架已自动更新")
        print(f"   下次运行将生成第 {chapter_num + 1} 章")
        
        return chapter_text


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="故事续写流水线")
    parser.add_argument("chapter", nargs="?", type=int, help="章节号（默认自动递增）")
    parser.add_argument("--feedback", "-f", type=str, help="用户反馈")
    parser.add_argument("--comments", "-c", type=str, help="读者评论JSON文件")
    parser.add_argument("--dry-run", action="store_true", help="只构建prompt，不生成")
    args = parser.parse_args()
    
    pipeline = StoryPipeline()
    
    if args.dry_run:
        pipeline.load_framework()
        pipeline.collect_inputs(args.feedback, args.comments)
        ch = args.chapter or pipeline.framework["meta"].get("chapter_count", 1) + 1
        prompt = pipeline.build_prompt(ch)
        print(f"\n{'='*60}")
        print("📋 生成的 Prompt (前500字):")
        print(f"{'='*60}")
        print(prompt[:500])
    else:
        pipeline.run(chapter_num=args.chapter, feedback=args.feedback, comments_file=args.comments)
