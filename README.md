# 弹幕评论区智能分析

输入一个 B站 BV 号，几分钟内拿到这条视频的观众复盘报告。

## 功能

- 🔍 **数据采集** — 自动拉取视频弹幕和评论
- 🧹 **清洗去重** — 规则过滤 + LLM 辅助识别刷屏/灌水
- 📊 **聚类分析** — TF-IDF + KMeans 提取弹幕/评论主题
- 🤖 **智能归纳** — Qwen3-0.6B 生成主题名、情感分析、争议度判断
- 📝 **复盘报告** — 5 条复盘结论 + Top5 可执行建议
- 🌐 **Web 界面** — 输入 BV 号，实时查看分析进度和结果

## 快速开始

### 方式一：Web 界面（推荐）

```bash
# 安装依赖
pip install -r requirements.txt

# 设置 HuggingFace 镜像（国内环境）
export HF_ENDPOINT=https://hf-mirror.com

# 启动服务
python server.py

# 打开浏览器访问 http://localhost:8000
```

### 方式二：命令行

```bash
# 1. 采集数据
python fetch_video.py BV117411r7R1

# 2. 分析（首次运行会自动下载 Qwen3-0.6B 模型）
export HF_ENDPOINT=https://hf-mirror.com
python analyze_video.py BV117411r7R1

# 报告输出到 output/BV117411r7R1/report.json
```

## 命令行参数

### fetch_video.py — 数据采集

```
python fetch_video.py <BV号或链接> [选项]

选项:
  --max-comments N    最多采集 N 条根评论 (默认: 500)
  --output-dir DIR    输出目录 (默认: ./output)
  --delay FLOAT       请求间隔秒数 (默认: 0.3)
  --skip-danmaku      跳过弹幕采集
  --skip-comments     跳过评论采集
```

### analyze_video.py — 智能分析

```
python analyze_video.py <BV号或数据目录> [选项]

选项:
  --model MODEL       LLM 模型名 (默认: Qwen/Qwen3-0.6B)
  --output-dir DIR    输出目录 (默认: ./output)
  --skip-clean        跳过清洗步骤
```

### server.py — Web 服务

```
python server.py

环境变量:
  HF_ENDPOINT    HuggingFace 镜像地址 (默认: https://hf-mirror.com)
  LLM_MODEL      LLM 模型名 (默认: Qwen/Qwen3-0.6B)
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 界面 |
| GET | `/api/analyze/stream?bvid=xxx` | SSE 流式分析（采集+分析+实时进度） |
| GET | `/api/report/{bvid}` | 获取已有报告（缓存） |

## 输出结构

```
output/{BV号}/
├── video_info.json   视频元信息
├── danmaku.json      弹幕原始数据
├── comments.json     评论原始数据
└── report.json       分析报告（供前端消费）
```

### report.json 字段说明

```json
{
  "video":    { "title", "up", "play", "dm", "cm" },
  "dmThemes": [{ "n": "主题名", "c": 数量, "t": "时段" }],
  "peaks":    [{ "tm": "时间", "x": "倍数", "n": 数量, "s": "叙事" }],
  "cmThemes": [{ "n": "主题名", "c": 数量, "pct": 占比, "dis": "争议度",
                 "q": [{ "t": "引文", "l": 赞数, "r": 回复数, "k": "pro/con" }],
                 "note": "编辑注释" }],
  "slots":    [{ "h": "问题", "p": "回答", "r": "溯源" }],
  "acts":     [{ "t": "建议", "s": "依据" }],
  "logs":     [["步骤描述", "耗时"]],
  "meta":     { "model", "elapsed", "clean_stats" }
}
```

## 项目结构

```
data-pipeline/
├── server.py                     Web 服务 (FastAPI + SSE)
├── fetch_video.py                数据采集 CLI
├── analyze_video.py              分析管线 CLI
├── danmaku-comment-insight-demo.html  前端页面
├── requirements.txt
├── README.md
├── bilibili/                     B站 API 封装
│   ├── video.py                  视频信息
│   ├── danmaku.py                弹幕采集 (XML)
│   └── comment.py                评论采集
├── analysis/                     分析模块
│   ├── llm.py                    LLM 封装 (Qwen3-0.6B)
│   ├── clean.py                  清洗去重
│   ├── danmaku_analysis.py       弹幕峰值检测 + 主题聚类
│   ├── comment_analysis.py       评论主题聚类 + 情感分析
│   └── report.py                 报告生成 (slots + acts)
└── output/                       采集和分析结果
```

## 技术栈

- **采集**: requests + B站公开 API
- **分析**: jieba 分词 + scikit-learn (TF-IDF/KMeans) + Qwen3-0.6B
- **后端**: FastAPI + SSE 流式推送
- **前端**: 纯 HTML/CSS/JS，无框架依赖
- **硬件**: 需要 GPU（Qwen3-0.6B 占用约 1.1GB 显存）

## Docker 部署

### 方式 A：轻量构建（推荐，首次启动自动下载模型）

```bash
# 构建镜像
docker build -t danmaku-insight .

# 运行（需要 NVIDIA GPU + nvidia-docker）
docker run --gpus all -p 8000:8000 \
  -v ./output:/app/output \
  danmaku-insight

# 打开 http://localhost:8000
```

首次启动会自动从 HuggingFace 镜像站下载 Qwen3-0.6B（约 1.2GB），之后通过 volume 缓存不再重复下载。

### 方式 B：模型预装（镜像自包含，拿来即用）

```bash
# 构建时打包模型（镜像约 +1.2GB，但启动即用）
docker build --build-arg PRELOAD_MODEL=1 -t danmaku-insight:full .

docker run --gpus all -p 8000:8000 \
  -v ./output:/app/output \
  danmaku-insight:full
```

### 使用 docker-compose

```bash
# 一键启动（含 GPU 配置）
docker compose up

# 后台运行
docker compose up -d
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像地址（国内加速） |
| `LLM_MODEL` | `Qwen/Qwen3-0.6B` | LLM 模型名称 |

### 前提条件

- Docker 20.10+
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) (nvidia-docker)
- NVIDIA GPU（Qwen3-0.6B 需约 1.1GB 显存）

## 注意事项

- 首次运行会从 HuggingFace 下载 Qwen3-0.6B 模型（约 1.2GB）
- 国内环境需设置 `export HF_ENDPOINT=https://hf-mirror.com`
- 无需 B站登录态，使用公开 API
- 弹幕接口有实时池上限（约 1200 条），历史弹幕需登录态
- 未登录时评论按热度排序可能只返回少量根评论，子评论可正常拉取
