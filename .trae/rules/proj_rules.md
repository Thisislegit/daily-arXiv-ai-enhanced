# 项目逻辑架构文档

## 1. 项目整体功能概述
本项目是一个自动化的 arXiv 论文追踪与 AI 增强系统，旨在每日自动抓取计算机科学（如 CV、CL）领域的最新论文，利用大语言模型（LLM）生成结构化摘要（TL;DR、动机、方法、结论），并通过 Web 界面和 Markdown 报告进行展示。

## 2. 主要模块划分
* 数据采集模块: 负责从 arXiv 网站爬取最新的论文元数据。
* AI 增强模块: 利用 LLM 对爬取的论文进行深度分析、摘要生成和敏感内容检测。
* 数据处理与转换模块: 负责数据去重、格式转换（JSONL 转 Markdown）及文件列表更新。
* 表现层模块 (Presentation Layer): 提供静态 Web 界面，动态加载并展示增强后的论文数据。

## 3. 关键文件功能说明
* [arxiv.py](daily_arxiv/daily_arxiv/spiders/arxiv.py) (数据采集): Scrapy 爬虫核心文件，负责定义爬取规则、解析 arXiv 列表页及提取论文元数据。
* [enhance.py](ai/enhance.py) (AI 增强): 调用 LLM API 处理论文摘要，生成结构化分析结果并保存为 JSONL 格式。
* [convert.py](to_md/convert.py) (辅助工具): 将增强后的 JSONL 数据转换为易读的 Markdown 每日报告。
* [app.js](js/app.js) (表现层): 前端核心逻辑，负责读取数据文件、渲染论文卡片及处理交互（筛选、搜索）。
* [run.yml](.github/workflows/run.yml) (核心业务): GitHub Actions 工作流配置文件，编排每日定时任务（爬取 -> 去重 -> 增强 -> 部署）。

## 4. 数据流向示意图

1. 采集: `arXiv Website` -> [Scrapy Spider] -> `data/YYYY-MM-DD.jsonl` (原始数据)
2. 去重: `data/YYYY-MM-DD.jsonl` -> [check_stats.py] -> (验证是否有新内容)
3. 增强: `data/YYYY-MM-DD.jsonl` -> [enhance.py] -> `data/YYYY-MM-DD_AI_enhanced_Language.jsonl` (增强数据)
4. 展示 (Web): `data/..._enhanced.jsonl` -> [app.js] -> `index.html` (用户界面)
5. 归档 (Markdown): `data/..._enhanced.jsonl` -> [convert.py] -> `data/YYYY-MM-DD.md` (Markdown 报告)