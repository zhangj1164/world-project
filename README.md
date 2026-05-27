# 《春秋》AI 续写项目

> 基于 DeepSeek V4 Pro 的小说分析 + 续作生成流水线

## 项目结构

```
├── src/
│   ├── analyzer/       # 小说分析器
│   │   ├── novel_analyzer.py   分块分析 + 角色SOUL生成
│   │   ├── progress_watch.py   CMD进度监控窗口
│   │   └── progress_server.py  进度HTTP服务
│   ├── merge/
│   │   └── character_merge.py  别名去重合并
│   ├── framework/
│   │   ├── build_framework.py  故事框架构建
│   │   ├── gen_outline.py      章节大纲生成
│   │   └── update_framework.py 框架状态更新
│   └── pipeline/
│       └── story_pipeline.py   续写流水线 Agent
│
├── data/
│   ├── chunqiu-txt/          原小说TXT
│   └── novel_analysis/       分析产出
│       ├── checkpoints/      分块分析断点
│       ├── characters/       原始角色SOUL（827个）
│       ├── characters_merged/ 别名合并SOUL（164个）
│       ├── chapter_summaries.json
│       ├── stage_summaries.json
│       └── global_summary.json
│
├── output/
│   └── story_framework/      框架+续作产出
│       ├── story_framework.json  续作生成总控
│       ├── world_SOUL.md         世界观灵魂
│       ├── timeline_SOUL.md      时间线
│       ├── chapter_outline.json  章节大纲
│       └── sequel_chapter_*.md   续作章节
│
├── tools/
│   └── 查看进度.bat
│
├── .env.example     环境变量模板
└── .gitignore
```

## 快速开始

### 1. 配置
```bash
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key
```

### 2. 从零分析小说
```bash
python src/analyzer/novel_analyzer.py "data/chunqiu-txt/春秋人生之重合.txt"
```

### 3. 构建故事框架
```bash
python src/framework/build_framework.py
```

### 4. 生成续作章节（流水线）
```bash
# 自动生成下一章
python src/pipeline/story_pipeline.py

# 指定章节
python src/pipeline/story_pipeline.py 3

# 带用户反馈
python src/pipeline/story_pipeline.py --feedback "诺诺的戏份不够"

# 带读者评论（未来）
python src/pipeline/story_pipeline.py --comments comments.json
```

## 流水线阶段

1. **加载框架** → 读取 story_framework.json
2. **收集输入** → 用户反馈 / 读者评论 / 角色SOUL
3. **构建提示** → 大纲 + 前章上下文 + 外部输入
4. **AI生成** → DeepSeek V4 Pro 创作
5. **更新状态** → 自动刷新 current_state + 伏笔

## 技术栈

- Python 3.13 + OpenAI SDK
- DeepSeek V4 Pro (deepseek-v4-pro)
- 项目托管: GitHub (world-project)
