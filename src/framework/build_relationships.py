"""
角色关系图谱构建器
=================
从合并SOUL + 原著数据中提取，生成可供续写流水线使用的完整关系图。
"""
import json, re, os
from pathlib import Path
from collections import defaultdict

CHAR_DIR = Path("data/novel_analysis/characters_merged")
OUTPUT = Path("output/story_framework/character_relationships.json")

# 核心角色 + 称呼约定
ADDRESS_BOOK = {
    "天寒": {
        "aliases": ["独孤天寒", "寒", "天寒哥哥"],
        "called_by": {
            "肥鸭": {"term": "老大", "tone": "死党/小弟，表面调侃内心崇拜"},
            "诺诺": {"term": "天寒", "tone": "恋人，亲密自然"},
            "阿紫": {"term": "哥 / 天寒哥哥", "tone": "义妹，依赖撒娇"},
            "小猪": {"term": "老大", "tone": "朋友，服从"},
            "绯雨": {"term": "天寒", "tone": "好友兼暗恋（后期释然），常捉弄"},
            "小龙": {"term": "哥哥 / 主人", "tone": "宠物依赖"},
            "小雪": {"term": "哥哥 / 主人", "tone": "宠物依赖"},
            "快刀浪子": {"term": "老大", "tone": "敬服又嫉妒"},
            "陆易": {"term": "老大", "tone": "死党，绝对信任"},
            "石大夫": {"term": "天寒 / 小子", "tone": "忘年交，长辈关爱"},
            "莫嫣雨": {"term": "天寒", "tone": "师姐弟，好感萌生"},
            "幽心": {"term": "主人 / 天寒", "tone": "主仆，如姐弟"},
            "鲁将军": {"term": "天寒 / 小子", "tone": "忘年交，师徒"},
            "文言": {"term": "天寒", "tone": "忘年交，商业伙伴"},
            "柳生渡边": {"term": "天寒 / 九州玩家", "tone": "敌对"},
        },
        "calls_others": {
            "肥鸭": "肥鸭、陆易",
            "诺诺": "诺诺",
            "阿紫": "阿紫",
            "小龙": "小家伙、小龙",
            "小雪": "小雪",
            "鲁将军": "鲁将军、鲁老",
        },
    },
    "肥鸭": {
        "aliases": ["陆易", "féi鸭", "鸭鸭"],
        "called_by": {
            "天寒": {"term": "肥鸭 / 陆易", "tone": "死党，调侃"},
            "诺诺": {"term": "肥鸭", "tone": "同伴"},
            "阿紫": {"term": "肥鸭哥 / 肥鸭", "tone": "好友"},
            "小猪": {"term": "肥鸭", "tone": "死党，互损"},
            "快刀浪子": {"term": "肥鸭", "tone": "损友"},
            "小龙": {"term": "鸭鸭", "tone": "宠物玩伴"},
        },
        "calls_others": {
            "天寒": "老大",
            "阿紫": "阿紫",
            "小猪": "小猪",
            "诺诺": "诺诺 / 大嫂",
        },
    },
    "诺诺": {
        "aliases": [],
        "called_by": {
            "天寒": {"term": "诺诺", "tone": "恋人，温柔"},
            "绯雨": {"term": "诺诺", "tone": "闺蜜"},
            "肥鸭": {"term": "诺诺 / 大嫂", "tone": "开玩笑"},
            "阿紫": {"term": "诺诺姐", "tone": "姐妹淘"},
            "鲁艺": {"term": "诺诺姐姐", "tone": "晚辈尊敬"},
        },
        "calls_others": {
            "天寒": "天寒",
            "绯雨": "绯雨",
            "爷爷奶奶": "爷爷、奶奶",
        },
    },
    "阿紫": {
        "aliases": ["紫垣旋忆"],
        "called_by": {
            "天寒": {"term": "阿紫", "tone": "义妹，爱护"},
            "肥鸭": {"term": "阿紫", "tone": "好友，如妹妹"},
            "小雪": {"term": "阿紫姐姐", "tone": "依赖"},
            "小龙": {"term": "阿紫", "tone": "亲近"},
            "鲁将军": {"term": "阿紫 / 小丫头", "tone": "长辈喜爱"},
        },
        "calls_others": {
            "天寒": "哥 / 天寒哥哥",
            "肥鸭": "肥鸭哥",
            "小雪": "小雪",
        },
    },
    "小龙": {
        "aliases": ["小玉龙", "宝宝", "小龙宝宝", "小家伙"],
        "called_by": {
            "天寒": {"term": "小家伙 / 小龙", "tone": "宠物伙伴，溺爱"},
            "小雪": {"term": "宝宝", "tone": "欢喜冤家"},
            "阿紫": {"term": "小龙宝宝", "tone": "宠物，宠爱"},
            "肥鸭": {"term": "小家伙", "tone": "玩伴"},
        },
        "calls_others": {
            "天寒": "哥哥",
            "小雪": "小雪",
            "阿紫": "阿紫",
        },
    },
    "绯雨": {
        "aliases": [],
        "called_by": {
            "诺诺": {"term": "绯雨", "tone": "闺蜜"},
            "天寒": {"term": "绯雨", "tone": "好友"},
            "肥鸭": {"term": "绯雨", "tone": "损友"},
        },
        "calls_others": {
            "诺诺": "诺诺",
            "天寒": "天寒",
            "肥鸭": "肥鸭",
        },
    },
    "小雪": {
        "aliases": [],
        "called_by": {
            "天寒": {"term": "小雪", "tone": "宠物，爱护"},
            "阿紫": {"term": "小雪", "tone": "宠物，宠爱"},
            "小龙": {"term": "小雪", "tone": "玩伴"},
            "诺诺": {"term": "小雪", "tone": "喜欢"},
        },
        "calls_others": {
            "天寒": "天寒哥哥",
            "阿紫": "阿紫姐姐",
            "小龙": "宝宝",
        },
    },
    "快刀浪子": {
        "aliases": ["浪子"],
        "called_by": {
            "天寒": {"term": "快刀浪子 / 浪子", "tone": "队友"},
            "肥鸭": {"term": "浪子", "tone": "损友"},
            "彩霞": {"term": "浪子", "tone": "女友"},
            "小猪": {"term": "浪子", "tone": "对头式队友"},
        },
        "calls_others": {
            "天寒": "老大",
            "彩霞": "彩霞",
            "肥鸭": "肥鸭",
        },
    },
    "石大夫": {
        "aliases": ["老石"],
        "called_by": {
            "天寒": {"term": "石大夫 / 石老", "tone": "忘年交，尊敬"},
            "玄真道长": {"term": "石老头 / 石老弟", "tone": "老友"},
        },
        "calls_others": {
            "天寒": "天寒 / 小子",
        },
    },
    "莫嫣雨": {
        "aliases": ["莫雨嫣"],
        "called_by": {
            "天寒": {"term": "莫嫣雨 / 莫师姐", "tone": "师姐弟"},
            "言正": {"term": "嫣雨 / 表妹", "tone": "表兄妹"},
        },
        "calls_others": {
            "天寒": "天寒",
            "言正": "言正 / 表兄",
        },
    },
    "鲁将军": {
        "aliases": ["鲁群", "鲁老爷子", "鲁艺"],
        "called_by": {
            "天寒": {"term": "鲁将军 / 鲁老", "tone": "忘年交"},
            "阿紫": {"term": "鲁将军", "tone": "尊敬"},
            "诺诺": {"term": "鲁爷爷", "tone": "长辈"},
        },
        "calls_others": {
            "天寒": "天寒 / 小子",
            "阿紫": "阿紫 / 小丫头",
        },
    },
    "文言": {
        "aliases": ["文老头", "文副掌门"],
        "called_by": {
            "天寒": {"term": "文言 / 文老", "tone": "忘年交，商业伙伴"},
        },
        "calls_others": {
            "天寒": "天寒",
        },
    },
    "幽心": {
        "aliases": ["幽氏姐妹"],
        "called_by": {
            "天寒": {"term": "幽心", "tone": "信任的下属/如姐"},
        },
        "calls_others": {
            "天寒": "天寒 / 主人",
        },
    },
    "小猪": {
        "aliases": ["猪猪", "减肥专家"],
        "called_by": {
            "天寒": {"term": "小猪", "tone": "好友"},
            "肥鸭": {"term": "小猪", "tone": "死党，互损"},
            "快刀浪子": {"term": "小猪", "tone": "对头式队友"},
        },
        "calls_others": {
            "天寒": "老大",
            "肥鸭": "肥鸭",
        },
    },
}

# 关系矩阵（B对A的称呼）
def build_full_graph():
    """基于原始数据补充完整关系图"""
    
    # 从合并SOUL提取关系
    soul_rels = {}
    for sf in CHAR_DIR.glob("*_SOUL.md"):
        name = sf.stem.replace("_SOUL", "")
        with open(sf, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r'## relationships\n\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
        if m:
            rels = []
            for line in m.group(1).strip().split("\n"):
                if line.startswith("- **"):
                    rels.append(line.strip("- "))
            if rels:
                soul_rels[name] = rels
    
    # 输出完整图谱
    graph = {
        "meta": {
            "version": "2.0",
            "description": "角色关系图谱 + 称呼约定。续写时必须严格遵守称呼方式。",
            "note": "每个角色调用 others 时查阅 called_by 字段，确定正确称呼",
        },
        "address_book": ADDRESS_BOOK,
        "soul_relationships": soul_rels,
        "usage_guide": {
            "how": "生成章节时，始终使用 called_by 中定义的称呼。如：肥鸭叫天寒只能叫'老大'，不能叫'天寒'或'寒兄'。",
            "tone": "保持 called_by.tone 中的情感基调。",
            "examples": [
                "肥鸭→天寒: '老大，起来了没？' ✅",
                "肥鸭→天寒: '天寒兄，早安。' ❌ 称呼错误",
                "阿紫→天寒: '哥！你又胡来！' ✅",
                "诺诺→天寒: '天寒，别逞强。' ✅",
                "小龙→天寒: '哥哥！我要吃那个！' ✅",
            ],
        },
    }
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 关系图谱已生成: {OUTPUT}")
    print(f"   收录角色: {len(ADDRESS_BOOK)} 个")
    print(f"   SOUL关系: {len(soul_rels)} 个角色")
    return graph


if __name__ == "__main__":
    build_full_graph()
