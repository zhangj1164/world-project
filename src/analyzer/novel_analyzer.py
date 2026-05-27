"""
《春秋》小说拆解分析系统
========================
功能：
  1. 按章节分块，调用 DeepSeek API 逐块分析
  2. 提取：章节摘要、人物特征、世界观元素
  3. 渐进合并生成：章节总结、阶段总结、角色 SOUL.md

用法：
  python novel_analyzer.py <小说文件.txt> [--api-key YOUR_KEY]
"""

import os
import re
import json
import time
import sys
import hashlib
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 自动加载 .env 配置
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# ============================================================
# 配置
# ============================================================

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

OUTPUT_DIR = Path("data/novel_analysis")
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"
CHARACTER_DIR = OUTPUT_DIR / "characters"
PHASE_FILE = OUTPUT_DIR / "phase_progress.json"

def update_phase(phase: str, done: int, total: int, msg: str = ""):
    """写入阶段进度文件，供 progress_watch.py 读取"""
    PHASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PHASE_FILE, "w", encoding="utf-8") as f:
        json.dump({"phase": phase, "done": done, "total": total, "msg": msg, "time": time.time()}, f)

CHUNK_SIZE = 30000       # 每块约 3 万字符
MAX_WORKERS = 3          # 并发 API 调用数
RATE_LIMIT_DELAY = 1.0   # 每次 API 调用间隔（秒）

# ============================================================
# 工具函数
# ============================================================

def detect_chapters(text: str) -> list[dict]:
    """检测章节边界，返回 [(标题, 内容, 起始位置), ...]"""
    patterns = [
        r'(第[零一二三四五六七八九十百千万\d]+[章])\s*(.*?)(?=\n|$)',
        r'(Chapter\s*\d+)\s*(.*?)(?=\n|$)',
        r'([序跋终尾声])',
    ]
    
    chapters = []
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.MULTILINE))
        if len(matches) >= 3:  # 至少找到 3 个才认为是有效模式
            for i, m in enumerate(matches):
                title = m.group(0).strip()
                start = m.start()
                end = matches[i+1].start() if i+1 < len(matches) else len(text)
                content = text[start:end]
                chapters.append({"title": title, "start": start, "content": content})
            break
    
    return chapters


def chunk_text(text: str, chapter_info: list[dict]) -> list[dict]:
    """将文本按章节或固定大小分块"""
    chunks = []
    
    if chapter_info and len(chapter_info) > 1:
        # 按章节分块
        for i, ch in enumerate(chapter_info):
            chunk_id = f"ch{i+1:04d}"
            # 如果单章太长，继续切分
            if len(ch["content"]) > CHUNK_SIZE * 2:
                sub_chunks = []
                for j in range(0, len(ch["content"]), CHUNK_SIZE):
                    sub = ch["content"][j:j+CHUNK_SIZE]
                    sub_chunks.append({
                        "id": f"{chunk_id}_part{j//CHUNK_SIZE+1}",
                        "title": ch["title"],
                        "part": j//CHUNK_SIZE + 1,
                        "content": sub,
                    })
                chunks.extend(sub_chunks)
            else:
                chunks.append({
                    "id": chunk_id,
                    "title": ch["title"],
                    "part": 1,
                    "content": ch["content"],
                })
    else:
        # 按固定大小分块
        for i in range(0, len(text), CHUNK_SIZE):
            chunk_content = text[i:i+CHUNK_SIZE]
            chunks.append({
                "id": f"ch{i//CHUNK_SIZE+1:04d}",
                "title": "未识别章节",
                "part": 1,
                "content": chunk_content,
            })
    
    return chunks


def content_hash(content: str) -> str:
    return hashlib.md5(content[:1000].encode()).hexdigest()[:8]


# ============================================================
# DeepSeek API 调用
# ============================================================

ANALYSIS_SYSTEM_PROMPT = """你是一位资深文学分析师，正在分析一部名为《春秋》的长篇小说的章节。

请对以下文本片段进行结构化分析，输出严格 JSON 格式：

{
  "chapter_title": "章节标题（如果能识别出来）",
  "summary": "本章内容摘要（200字以内）",
  "key_events": ["事件1", "事件2", ...],
  "characters_appeared": [
    {
      "name": "角色名",
      "actions": "本章中做了什么",
      "traits_shown": "体现出的性格特点",
      "speech_style": "说话风格",
      "relationships": "与他人的关系变化"
    }
  ],
  "worldbuilding": ["世界观元素1", "世界观元素2", ...],
  "tone": "本章氛围/基调",
  "timeline_position": "在时间线中的位置（如能判断）",
  "themes": ["主题1", "主题2"]
}

注意：
- 如果文本片段只是某章的一部分，标注 part_info
- 角色名必须保持一致，同一角色不要用不同名字
- 只提取确定的信息，不确定的不要编造
"""

MERGE_SYSTEM_PROMPT = """你是文学分析合并专家。你会收到多份章节分析 JSON，请合并为一份连贯的总结。

输出格式：
{
  "stage_name": "阶段名称",
  "stage_summary": "该阶段整体故事摘要（500字以内）",
  "major_plot_points": ["关键情节点1", "关键情节点2"],
  "character_developments": {
    "角色名": "该阶段内的角色发展"
  },
  "worldbuilding_updates": ["新增或改变的世界观元素"],
  "timeline_range": "时间线范围"
}
"""

CHARACTER_PROMPT = """你是角色分析专家。以下是关于角色「{name}」在小说不同阶段的所有记录。
请综合所有信息，生成该角色的 SOUL.md 文件内容。

输出严格的 JSON：
{
  "name": "角色名",
  "aliases": ["别名1", "别名2"],
  "first_appearance": "首次登场章节",
  "role": "在故事中的角色定位",
  "personality_traits": ["特质1", "特质2", "特质3"],
  "core_beliefs": ["核心信念1", "核心信念2"],
  "behavior_patterns": ["行为模式1", "行为模式2"],
  "speech_style": "语言风格描述",
  "relationships": {"角色名": "关系描述"},
  "character_arc": "角色弧光的整体描述",
  "key_moments": ["关键时刻1", "关键时刻2"],
  "secrets_or_conflicts": "内心的秘密或矛盾",
  "soul_summary": "一句话灵魂描述"
}
"""


class DeepSeekClient:
    def __init__(self):
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        # 加载多个 API Key
        self.keys = []
        # 兼容旧配置 DEEPSEEK_API_KEY
        single_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if single_key:
            self.keys.append(single_key)
        # 读取 DEEPSEEK_API_KEY_1, _2, _3 ...
        for i in range(1, 10):
            k = os.environ.get(f"DEEPSEEK_API_KEY_{i}", "")
            if k:
                self.keys.append(k)
        
        if not self.keys:
            self.keys = [""]
        
        self.key_index = 0
        self._client = None
        self._client_lock = Lock()
        self.lock = Lock()
        self.call_count = 0
    
    @property
    def current_key(self):
        return self.keys[self.key_index % len(self.keys)]
    
    def _get_client(self):
        """获取或重建 OpenAI 客户端"""
        with self._client_lock:
            if self._client is None:
                self._client = OpenAI(
                    api_key=self.current_key,
                    base_url=self.base_url,
                    timeout=180.0,
                    max_retries=0,
                )
            return self._client
    
    def _rotate_key(self):
        """切换到下一个 Key，重建客户端"""
        with self._client_lock:
            self.key_index = (self.key_index + 1) % len(self.keys)
            self._client = OpenAI(
                api_key=self.current_key,
                base_url=self.base_url,
                timeout=180.0,
                max_retries=0,
            )
            return self._client
    
    def call(self, system_prompt: str, user_content: str, 
             max_tokens: int = 4096, temperature: float = 0.3) -> dict | None:
        """调用 DeepSeek API，返回解析后的 JSON；失败自动切换 Key"""
        with self.lock:
            self.call_count += 1
            call_id = self.call_count
        
        for attempt in range(5):
            try:
                time.sleep(RATE_LIMIT_DELAY)
                client = self._get_client()
                response = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                result = response.choices[0].message.content
                return json.loads(result)
            except json.JSONDecodeError:
                print(f"  ⚠ 调用 #{call_id} JSON 解析失败，重试 {attempt+1}/5")
                time.sleep(3)
            except Exception as e:
                err = str(e)
                
                # 提取 HTTP 状态码和响应体
                status_code = ""
                error_body = ""
                if hasattr(e, 'status_code'):
                    status_code = f" [{e.status_code}]"
                if hasattr(e, 'body') and e.body:
                    error_body = str(e.body)[:200]
                    if 'error' in error_body.lower():
                        import json as _json
                        try:
                            body_obj = _json.loads(error_body) if isinstance(e.body, str) else e.body
                            error_body = str(body_obj.get('error', {}))[:200]
                        except: pass
                
                detail = f"HTTP{status_code}"
                if error_body:
                    detail += f" | {error_body}"
                
                if "429" in err or "rate" in err.lower():
                    self._rotate_key()
                    wait = (attempt + 1) * 30
                    print(f"  ⏳ Key{self.key_index%len(self.keys)+1} 429 限流{detail}, {wait}s 后换Key...")
                elif "Connection" in err or "connect" in err.lower():
                    self._rotate_key()
                    wait = [10, 30, 60, 120, 180][attempt]
                    print(f"  🔌 Key{self.key_index%len(self.keys)+1} 连接失败{detail}, 换Key {wait}s后重试 ({attempt+1}/5)")
                else:
                    wait = [5, 15, 30, 60, 120][attempt]
                    print(f"  ⚠ 调用 #{call_id} 失败{detail}: {err[:60]}, {wait}s后重试 ({attempt+1}/5)")
                time.sleep(wait)
        return None


# ============================================================
# 分析流水线
# ============================================================

def analyze_chunk(client: DeepSeekClient, chunk: dict, prev_context: str = "") -> dict:
    """分析单个文本块"""
    chunk_id = chunk["id"]
    title = chunk.get("title", "未知")
    content = chunk["content"]
    
    # 截断过长的内容（DeepSeek 上下文有限）
    max_input = 25000
    if len(content) > max_input:
        content = content[:max_input] + "\n\n... [内容过长，已截断] ..."
    
    user_prompt = f"""章节标题/位置：{title}（第 {chunk.get('part', 1)} 部分）
    
前文上下文：{prev_context if prev_context else '无（这是开头部分）'}

=== 文本内容 ===
{content}
"""
    result = client.call(ANALYSIS_SYSTEM_PROMPT, user_prompt, max_tokens=4096)
    if result:
        result["_chunk_id"] = chunk_id
        result["_source_title"] = title
    return result


def merge_analyses(client: DeepSeekClient, analyses: list[dict], 
                   stage_name: str) -> dict:
    """合并多个章节分析为一个阶段总结"""
    combined = json.dumps(analyses, ensure_ascii=False, indent=2)
    
    user_prompt = f"""请将以下 {len(analyses)} 个章节的分析合并为阶段总结。

阶段名称：{stage_name}

=== 分析数据 ===
{combined[:10000]}
"""
    result = client.call(MERGE_SYSTEM_PROMPT, user_prompt, max_tokens=4096)
    return result


def generate_character_soul(client: DeepSeekClient, name: str, 
                            records: list[dict]) -> dict:
    """为单个角色生成 SOUL.md"""
    combined = json.dumps(records, ensure_ascii=False, indent=2)
    sys_prompt = CHARACTER_PROMPT.replace("{name}", name)
    
    user_prompt = f"""角色名：{name}

=== 该角色在小说中的所有记录 ===
{combined[:12000]}
"""
    result = client.call(sys_prompt, user_prompt, max_tokens=4096)
    return result


# ============================================================
# 主流程
# ============================================================

def save_checkpoint(name: str, data):
    """保存检查点，支持断点续跑"""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHECKPOINT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_checkpoint(name: str) -> dict | None:
    path = CHECKPOINT_DIR / f"{name}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    if len(sys.argv) < 2:
        print("用法: python novel_analyzer.py <小说文件.txt>")
        print("环境变量: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL(可选)")
        sys.exit(1)
    
    novel_path = Path(sys.argv[1])
    if not novel_path.exists():
        print(f"❌ 文件不存在: {novel_path}")
        sys.exit(1)
    
    # 检查 Key：优先命令行参数 → 单一 KEY → 编号 KEY_1
    api_key = sys.argv[2] if len(sys.argv) > 2 else ""
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("DEEPSEEK_API_KEY_1", "")
    if not api_key:
        print("❌ 未找到 API Key，请在 .env 中设置 DEEPSEEK_API_KEY_1")
        sys.exit(1)
    
    os.environ["DEEPSEEK_API_KEY"] = api_key
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # ========== Phase 0: 读取文件 ==========
    print(f"\n{'='*60}")
    print(f"📖 正在读取: {novel_path.name}")
    print(f"{'='*60}")
    
    # 自动检测编码
    from charset_normalizer import from_path
    detected = from_path(str(novel_path)).best()
    encoding = detected.encoding if detected else "utf-8"
    print(f"  编码: {encoding}")
    
    with open(novel_path, "r", encoding=encoding, errors="replace") as f:
        text = f.read()
    
    total_chars = len(text)
    print(f"✅ 读取完成: {total_chars:,} 字符")
    
    # ========== Phase 1: 章节检测与分块 ==========
    print(f"\n🔍 检测章节边界...")
    chapter_info = detect_chapters(text)
    
    if chapter_info:
        print(f"✅ 检测到 {len(chapter_info)} 个章节")
    else:
        print(f"⚠ 未检测到明显的章节结构，将按固定大小分块")
    
    chunks = chunk_text(text, chapter_info)
    print(f"📦 共 {len(chunks)} 个分块待分析")
    
    # ========== Phase 2: 逐块分析 ==========
    print(f"\n{'='*60}")
    print(f"🤖 开始逐块分析（并发数: {MAX_WORKERS}）")
    print(f"{'='*60}\n")
    
    client = DeepSeekClient()
    
    # 检查断点续跑
    checkpoint = load_checkpoint("chunk_analyses")
    if checkpoint:
        print(f"🔄 从断点恢复，已完成 {len(checkpoint['results'])}/{len(chunks)} 块")
        results = checkpoint["results"]
        completed_ids = {r["_chunk_id"] for r in results if r}
        pending = [c for c in chunks if c["id"] not in completed_ids]
    else:
        results = []
        completed_ids = set()
        pending = list(chunks)
    
    print(f"⏳ 待处理: {len(pending)} 块\n")
    
    prev_context = ""
    
    for i, chunk in enumerate(pending):
        chunk_id = chunk["id"]
        print(f"[{i+1}/{len(pending)}] 分析 {chunk_id}: {chunk['title'][:30]}...", end=" ", flush=True)
        
        result = analyze_chunk(client, chunk, prev_context)
        
        if result:
            results.append(result)
            completed_ids.add(chunk_id)
            # 用当前摘要作为下一块的前文上下文
            prev_context = result.get("summary", "")
            print(f"✅ (摘要: {prev_context[:60]}...)")
        else:
            print(f"❌ 失败，将跳过")
        
        # 每块都保存检查点（防止进程被超时中断丢失数据）
        save_checkpoint("chunk_analyses", {"results": results, "total": len(chunks)})
        if (i + 1) % 10 == 0:
            print(f"  💾 检查点已保存 ({len(results)}/{len(chunks)})\n")
    
    # 最终保存
    save_checkpoint("chunk_analyses", {"results": results, "total": len(chunks)})
    
    valid_results = [r for r in results if r]
    print(f"\n✅ 逐块分析完成: {len(valid_results)}/{len(chunks)} 成功\n")
    
    # ========== Phase 3: 阶段合并 ==========
    print(f"{'='*60}")
    print(f"📊 阶段合并分析")
    print(f"{'='*60}")
    
    # 按章节或每 20 个块合并为一个阶段
    STAGE_SIZE = 20
    total_stages = (len(valid_results) + STAGE_SIZE - 1) // STAGE_SIZE
    
    # 断点续跑：加载已完成的阶段
    stages = load_checkpoint("stage_summaries") or []
    start_stage = len(stages)
    
    if start_stage > 0:
        print(f"🔄 从断点恢复，已完成 {start_stage}/{total_stages} 阶段\n")
    
    for i in range(start_stage * STAGE_SIZE, len(valid_results), STAGE_SIZE):
        batch = valid_results[i:i+STAGE_SIZE]
        stage_idx = i // STAGE_SIZE + 1
        stage_name = f"阶段{stage_idx}（第{i+1}-{min(i+STAGE_SIZE, len(valid_results))}块）"
        update_phase("阶段合并", stage_idx, total_stages, stage_name)
        
        print(f"  合并 {stage_name}...", end=" ", flush=True)
        merged = merge_analyses(client, batch, stage_name)
        if merged:
            stages.append(merged)
            save_checkpoint("stage_summaries", stages)  # 每阶段存盘
            print("✅")
        else:
            print("❌")
    
    save_checkpoint("stage_summaries", stages)
    print(f"✅ 阶段合并完成: {len(stages)} 个阶段\n")
    
    # ========== Phase 4: 角色提取与 SOUL.md 生成 ==========
    print(f"{'='*60}")
    print(f"👤 角色分析与 SOUL.md 生成")
    print(f"{'='*60}")
    
    # 从所有分析中汇总角色信息
    all_characters = {}
    for r in valid_results:
        chars = r.get("characters_appeared", [])
        for ch in chars:
            name = ch.get("name", "未知角色")
            if name not in all_characters:
                all_characters[name] = []
            all_characters[name].append(ch)
    
    print(f"  发现 {len(all_characters)} 个角色\n")
    
    # 只为主要角色生成 SOUL（出现次数 ≥ 5）
    major_chars = {k: v for k, v in all_characters.items() 
                   if len(v) >= 5 and k.strip() and not k.startswith('*')}
    minor_count = len(all_characters) - len(major_chars)
    if minor_count > 0:
        print(f"  略过 {minor_count} 个边缘角色（出现 < 5 次）\n")
    
    CHARACTER_DIR.mkdir(parents=True, exist_ok=True)
    
    total_chars = len(major_chars)
    done_chars = 0
    for idx, (char_name, records) in enumerate(major_chars.items(), 1):
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', char_name)
        soul_path = CHARACTER_DIR / f"{safe_name}_SOUL.md"
        
        # 断点续跑：跳过已生成的
        if soul_path.exists():
            done_chars += 1
            update_phase("角色SOUL生成", idx, total_chars, f"{char_name} (已跳过)")
            continue
        
        update_phase("角色SOUL生成", idx, total_chars, char_name)
        print(f"  [{idx}/{total_chars}] 生成 {char_name} 的 SOUL.md...", end=" ", flush=True)
        
        soul = generate_character_soul(client, char_name, records)
        if soul:
            # 写入 SOUL.md
            with open(soul_path, "w", encoding="utf-8") as f:
                f.write(f"# {char_name} — SOUL.md\n\n")
                f.write(f"> 自动生成于小说《春秋》分析\n\n")
                for key, val in soul.items():
                    if key == "name":
                        continue
                    f.write(f"## {key}\n\n")
                    if isinstance(val, list):
                        for item in val:
                            f.write(f"- {item}\n")
                    elif isinstance(val, dict):
                        for k, v in val.items():
                            f.write(f"- **{k}**: {v}\n")
                    else:
                        f.write(f"{val}\n")
                    f.write("\n")
                f.write("---\n")
                f.write(f"*由 DeepSeek AI 基于《春秋》全本分析生成*\n")
            print(f"✅")
        else:
            print(f"❌")
    
    # ========== Phase 5: 输出总报告 ==========
    print(f"\n{'='*60}")
    print(f"📝 生成总报告")
    print(f"{'='*60}")
    
    global_summary = {
        "novel_name": novel_path.stem,
        "total_characters": total_chars,
        "total_chunks": len(chunks),
        "chapters_detected": len(chapter_info),
        "characters_found": len(all_characters),
        "stages": len(stages),
        "character_list": list(all_characters.keys()),
    }
    
    report_path = OUTPUT_DIR / "global_summary.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(global_summary, f, ensure_ascii=False, indent=2)
    
    # 章节摘要
    chapter_summaries = []
    for r in valid_results:
        chapter_summaries.append({
            "title": r.get("_source_title", ""),
            "summary": r.get("summary", ""),
            "key_events": r.get("key_events", []),
            "tone": r.get("tone", ""),
        })
    
    with open(OUTPUT_DIR / "chapter_summaries.json", "w", encoding="utf-8") as f:
        json.dump(chapter_summaries, f, ensure_ascii=False, indent=2)
    
    # 阶段总结
    with open(OUTPUT_DIR / "stage_summaries.json", "w", encoding="utf-8") as f:
        json.dump(stages, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"🎉 分析完成！")
    print(f"{'='*60}")
    print(f"\n📁 输出目录: {OUTPUT_DIR.absolute()}")
    print(f"   ├── global_summary.json       全局分析概览")
    print(f"   ├── chapter_summaries.json    各章节摘要")
    print(f"   ├── stage_summaries.json      分阶段总结")
    print(f"   ├── characters/              角色 SOUL.md 文件")
    print(f"   └── checkpoints/             分析检查点")
    print(f"\n📊 统计:")
    print(f"   总字符数: {total_chars:,}")
    print(f"   分析块数: {len(valid_results)}/{len(chunks)}")
    print(f"   发现角色: {len(all_characters)}")
    print(f"   阶段总结: {len(stages)}")
    print(f"   API 调用: {client.call_count}")
    print(f"\n✨ 下一步: 使用角色 SOUL.md 和阶段总结来生成续作第一章")


if __name__ == "__main__":
    main()
