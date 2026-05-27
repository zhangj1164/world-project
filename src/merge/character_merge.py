"""
角色别名合并工具
=================
从分块分析结果中识别同一角色的不同称呼，
合并后重新生成统一的 SOUL.md。

用法：
  python character_merge.py
"""
import json
import os
import re
import time
from pathlib import Path
from openai import OpenAI

INPUT_DIR = Path("data/novel_analysis")
CHECKPOINT_FILE = INPUT_DIR / "checkpoints/chunk_analyses.json"
CHARACTER_DIR = INPUT_DIR / "characters_merged"  # 独立目录，不覆盖原始
MERGE_FILE = INPUT_DIR / "character_aliases.json"

def load_env():
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

def call_deepseek(system: str, user: str, key_index=0) -> dict | None:
    keys = []
    for i in range(1, 10):
        k = os.environ.get(f"DEEPSEEK_API_KEY_{i}", "")
        if k: keys.append(k)
    if not keys:
        keys = [os.environ.get("DEEPSEEK_API_KEY", "")]
    
    api_key = keys[key_index % len(keys)]
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    
    for attempt in range(5):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=180, max_retries=0)
            time.sleep(1)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=4096,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            err = str(e)
            wait = [5, 15, 30, 60, 120][attempt]
            if "401" in err or "429" in err:
                key_index = (key_index + 1) % len(keys)
                api_key = keys[key_index]
                wait = (attempt + 1) * 30
            print(f"  ⚠ 失败(Key{key_index+1}), {wait}s重试")
            time.sleep(wait)
    return None


def main():
    load_env()
    print("=" * 60)
    print("🔀 角色别名合并")
    print("=" * 60)
    
    # 1. 加载所有角色名
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        cp = json.load(f)
    results = [r for r in cp["results"] if r]
    
    all_names = {}
    for r in results:
        for ch in r.get("characters_appeared", []):
            name = ch.get("name", "").strip()
            if not name or name.startswith("*") or len(name) < 2:
                continue
            if name not in all_names:
                all_names[name] = []
            all_names[name].append(ch)
    
    names_list = sorted(all_names.keys())
    print(f"角色总数: {len(names_list)}")
    
    # 2. 分批用 AI 识别别名（每 30 个名字一批）
    BATCH_SIZE = 30
    TOTAL_BATCHES = (len(names_list) + BATCH_SIZE - 1) // BATCH_SIZE
    
    # 断点续跑：加载已识别的别名和完成的批次
    aliases = {}
    completed_batches = set()
    if MERGE_FILE.exists():
        with open(MERGE_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        aliases = {k: v for k, v in saved.items() if not k.startswith("_")}
        completed_batches = set(saved.get("_completed_batches", []))
        if aliases:
            print(f"🔄 从断点恢复，已有 {len(aliases)} 组别名, 已完成 {len(completed_batches)} 批\n")
    
    for i in range(0, len(names_list), BATCH_SIZE):
        batch_idx = i // BATCH_SIZE
        batch = names_list[i:i+BATCH_SIZE]
        
        # 跳过已完成的批次
        if batch_idx in completed_batches:
            continue
        
        print(f"\n分析批次 {batch_idx+1}/{TOTAL_BATCHES} ({len(batch)} 个)...")
        
        batch_str = "\n".join(f"- {n}" for n in batch)
        system = """你是角色别名识别专家。分析以下小说角色名列表，找出同一角色的不同称呼（别名）。
        
判断标准：
- 明显是同一人的不同叫法（如：天寒=独孤天寒，肥鸭=féi鸭）
- 称呼+括号变体（如：小家伙=小家伙（宝宝），小玉龙=小龙宝宝）
- 角色+特征描述（如：小家伙=宝宝，减肥专家=小猪=猪猪）
- 只合并明显的同名，不确定的不要强行合并

输出 JSON：
{
  "aliases": [
    {"canonical": "规范名（最常用或最完整的名字）", "aliases": ["别名1", "别名2"]},
    ...
  ],
  "not_merged": ["无法确定的名字1", "名字2"]
}"""

        result = call_deepseek(system, batch_str)
        if result:
            for group in result.get("aliases", []):
                canonical = group.get("canonical", "")
                if canonical:
                    aliases[canonical] = group.get("aliases", [])
            print(f"  ✅ 识别出 {len(result.get('aliases', []))} 组别名")
            # 每批后保存（含批次进度）
            completed_batches.add(batch_idx)
            save_data = dict(aliases)
            save_data["_completed_batches"] = list(completed_batches)
            with open(MERGE_FILE, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
        else:
            print(f"  ❌ 失败")
    
    # 3. 保存别名映射
    completed_batches.add(batch_idx)  # 标记全部完成
    save_data = dict(aliases)
    save_data["_completed_batches"] = list(completed_batches)
    with open(MERGE_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 别名映射已保存: {MERGE_FILE}")
    print(f"   共 {len(aliases)} 组别名关系")
    
    # 4. 合并记录并重新生成 SOUL
    print(f"\n{'='*60}")
    print("📝 合并角色记录...")
    print("=" * 60)
    
    # 构建 规范名 → {records: [...], aliases: [...]}
    merged = {}
    
    # 先建立反向映射: alias → canonical
    alias_to_canonical = {}
    for canonical, alias_list in aliases.items():
        for a in alias_list:
            alias_to_canonical[a.strip()] = canonical
        alias_to_canonical[canonical] = canonical  # 自己指向自己
    
    # 合并
    for name, records in all_names.items():
        canonical = alias_to_canonical.get(name, name)
        if canonical not in merged:
            merged[canonical] = {"records": [], "aliases": set()}
        merged[canonical]["records"].extend(records)
        if name != canonical:
            merged[canonical]["aliases"].add(name)
    
    print(f"合并后角色: {len(merged)} 个（原 {len(names_list)} 个）")
    
    # 只处理主要角色（出现 ≥ 5 次）
    major = {k: v for k, v in merged.items() if len(v["records"]) >= 5}
    print(f"主要角色: {len(major)} 个\n")
    
    # 5. 重新生成 SOUL.md（带别名信息）
    CHARACTER_DIR.mkdir(parents=True, exist_ok=True)
    
    for idx, (name, data) in enumerate(major.items(), 1):
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
        soul_path = CHARACTER_DIR / f"{safe_name}_SOUL.md"
        
        # 跳过已生成的
        if soul_path.exists():
            continue
        
        print(f"[{idx}/{len(major)}] {name} (别名: {', '.join(data['aliases'])[:40]})...", end=" ", flush=True)
        
        combined = json.dumps(data["records"], ensure_ascii=False)
        prompt = f"""角色名：{name}
别名：{', '.join(data['aliases']) if data['aliases'] else '无'}

=== 该角色在小说中的所有出现记录 （合并了所有别名）===
{combined[:12000]}

请生成 SOUL.md 内容 JSON：
{{
  "name": "规范名",
  "aliases": ["别名列表"],
  "role": "角色定位",
  "personality_traits": ["特质1", "特质2"],
  "core_beliefs": ["信念"],
  "behavior_patterns": ["行为模式"],
  "speech_style": "语言风格",
  "relationships": {{"角色名": "关系"}},
  "character_arc": "角色发展弧",
  "key_moments": ["关键时刻"],
  "soul_summary": "一句话灵魂"
}}"""

        system = f"你是角色分析专家，为{name}生成 SOUL.md。注意此人有多个别名，请整合所有记录。"
        soul = call_deepseek(system, prompt)
        
        if soul:
            with open(soul_path, "w", encoding="utf-8") as f:
                f.write(f"# {name} — SOUL.md\n\n")
                if data["aliases"]:
                    f.write(f"> 别名: {', '.join(data['aliases'])}\n\n")
                for key, val in soul.items():
                    if key in ("name", "aliases"):
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
            print("✅")
        else:
            print("❌")
    
    print(f"\n{'='*60}")
    print("✅ 别名合并完成！")
    print(f"   SOUL 文件: {CHARACTER_DIR}")
    print(f"   别名映射: {MERGE_FILE}")


if __name__ == "__main__":
    main()
