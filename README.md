# 弹幕评论区智能分析

输入一个 B站 BV 号，几分钟内拿到这条视频的观众复盘报告。

## 功能

- 🔍 **数据采集** — 自动拉取视频弹幕和评论
- 🧹 **清洗去重** — 规则过滤 + LLM 辅助识别刷屏/灌水
- 📊 **聚类分析** — TF-IDF + KMeans 提取弹幕/评论主题
- 🤖 **智能归纳** — LLM 生成主题名、情感分析、争议度判断
- 🔌 **可配置模型** — 本地模型 / OpenAI 兼容接口 / Anthropic，网页可视化配置
- 📝 **复盘报告** — 5 条复盘结论 + Top5 可执行建议
- 🌐 **Web 界面** — 输入 BV 号，实时查看分析进度和结果

## 快速开始

### 方式一：Web 界面（推荐）

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python server.py

# 打开浏览器访问 http://localhost:8000
# 在页面「模型设置」里选择后端、填 API Key，点「测试连接」验证后保存
```

默认后端是本地 Qwen3-0.6B（需要 GPU 和 `torch`/`transformers`）。想直接用云端 API、不装 torch，
在设置面板切到「OpenAI 兼容接口」或「Anthropic」，填地址和 Key 即可。

API Key 与接口地址**只从本地配置文件读取**（`config/llm.json`），不走环境变量。
不想用网页面板的话，也可以直接写这个文件：

```bash
mkdir -p config && cat > config/llm.json <<'JSON'
{
  "provider": "openai",
  "openai": {
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-xxx"
  }
}
JSON
chmod 600 config/llm.json
python server.py
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
  --comment-sort N    评论排序: 0=按时间 1=按热度 (默认: 1)
```

> 未登录时评论接口只返回降级响应，换排序也绕不过去，详见下文「评论采集限制」。

### analyze_video.py — 智能分析

```
python analyze_video.py <BV号或数据目录> [选项]

选项:
  --provider NAME     LLM 后端: local | openai | anthropic (默认读取已保存配置)
  --model MODEL       模型名称，覆盖配置
  --api-key KEY       API Key，覆盖配置（会留在 shell 历史里，更推荐写进 config/llm.json）
  --base-url URL      接口地址，覆盖配置
  --output-dir DIR    输出目录 (默认: ./output)
  --skip-clean        跳过清洗步骤
```

命令行参数只对本次运行生效，不会写入配置文件。

### server.py — Web 服务

```
python server.py
```

## 模型配置

支持三种后端。API Key 和接口地址只认配置文件 `config/llm.json`；
其余非敏感项（后端类型、模型名）可用环境变量，优先级为 **配置文件 > 环境变量 > 默认值**。

| 后端 | 说明 | 额外依赖 |
|------|------|----------|
| `local` | 本地 HuggingFace 模型（默认 Qwen3-0.6B） | GPU + `torch`、`transformers` |
| `openai` | 任何兼容 OpenAI `/chat/completions` 的服务 | 无（只用 `requests`） |
| `anthropic` | Anthropic Messages API | `anthropic` SDK |

`openai` 后端已内置这些服务的预设：OpenAI、DeepSeek、阿里云百炼（通义）、月之暗面 Kimi、
智谱 GLM、硅基流动 SiliconFlow、本地 Ollama。

### 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_PROVIDER` | `local` / `openai` / `anthropic`（默认 `local`） |
| `LLM_MODEL` | 当前后端的模型名 |
| `LLM_CONFIG_PATH` | 配置文件路径（默认 `./config/llm.json`） |
| `ALLOW_REMOTE_CONFIG` | 设为 `1` 才允许非本机修改配置，默认关闭 |
| `HF_ENDPOINT` | HuggingFace 镜像地址（仅 `local` 后端需要） |

注意这里**没有** `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `*_BASE_URL`。这几个名字在开发机上
经常已被别的工具占用（例如各类 CLI 会设置 `ANTHROPIC_BASE_URL` 指向内部网关），
一旦继承，本服务就会在用户不知情的情况下把提示词和密钥发往意料之外的地址。
所以密钥和接口地址只从配置文件读取。若环境里存在这些变量，设置面板会提示它们已被忽略。

### 关于密钥安全

API Key 只有一个来源：`config/llm.json`（权限 `0600`）。网页面板填写的 Key 以明文写入该文件，
页面上只回显脱敏值。需要注意：

- 本服务**没有任何鉴权**，因此配置读写与连通性测试默认只接受来自 `127.0.0.1` 的请求。
- 要在远端机器上用设置面板，需显式设置 `ALLOW_REMOTE_CONFIG=1`，并自行套一层 HTTPS
  和访问控制 —— 否则 Key 会经明文 HTTP 传输。
- `config/` 已在 `.gitignore` 里，不要提交。
- Docker 场景把宿主机的 `./config` 挂进容器，不要用 `-e` 传密钥（`-e` 会留在
  `docker inspect` 和 shell 历史里）。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 界面 |
| GET | `/api/analyze/stream?bvid=xxx` | SSE 流式分析（采集+分析+实时进度） |
| GET | `/api/report/{bvid}` | 获取已有报告（缓存） |
| GET | `/api/llm/config` | 读取当前模型配置（Key 已脱敏） |
| POST | `/api/llm/config` | 保存模型配置（默认仅本机） |
| POST | `/api/llm/test` | 测试模型连通性（默认仅本机） |

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
  "video":    { "title", "up", "play", "dm", "cm", "bvid", "cover", "duration" },
  "dmThemes": [{ "n": "主题名", "c": 数量, "t": "时段" }],
  "peaks":    [{ "tm": "时间", "x": "倍数", "n": 数量, "s": "叙事" }],
  "cmThemes": [{ "n": "主题名", "c": 数量, "pct": 占比, "dis": "争议度",
                 "q": [{ "t": "引文", "l": 赞数, "r": 回复数, "k": "pro/con",
                         "why": ["入选理由标签"] }],
                 "note": "编辑注释" }],
  "slots":    [{ "h": "问题", "p": "回答", "r": "溯源" }],
  "acts":     [{ "t": "建议", "s": "依据" }],
  "logs":     [["步骤描述", "耗时"]],
  "meta":     { "provider", "model", "backend", "elapsed", "clean_stats" }
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
│   ├── llm.py                    LLM 后端封装 (local/openai/anthropic)
│   ├── llm_config.py             模型配置读写与校验
│   ├── clean.py                  清洗去重
│   ├── danmaku_analysis.py       弹幕峰值检测 + 主题聚类
│   ├── comment_analysis.py       评论主题聚类 + 情感分析
│   └── report.py                 报告生成 (slots + acts)
├── config/                       模型配置（含 API Key，已 gitignore）
└── output/                       采集和分析结果
```

## 技术栈

- **采集**: requests + B站公开 API
- **分析**: jieba 分词 + scikit-learn (TF-IDF/KMeans) + LLM
- **后端**: FastAPI + SSE 流式推送
- **前端**: 纯 HTML/CSS/JS，无框架依赖
- **硬件**: 走云端 API 时无特殊要求；用本地 Qwen3-0.6B 需 GPU（约 1.1GB 显存）

## Docker 部署

### 方式 A：走云端 API（无需 GPU，最省事）

密钥写在宿主机的 `config/llm.json` 里，挂载进容器，不用 `-e` 传：

```bash
docker build -t danmaku-insight .

mkdir -p config && cat > config/llm.json <<'JSON'
{
  "provider": "openai",
  "openai": {
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-xxx"
  }
}
JSON
chmod 600 config/llm.json

docker run -p 8000:8000 \
  -v ./output:/app/output \
  -v ./config:/app/config \
  -e LLM_PROVIDER=openai \
  danmaku-insight

# 打开 http://localhost:8000
```

不需要 `--gpus`，启动时也会跳过模型下载。

### 方式 B：本地模型，首次启动自动下载

```bash
docker build -t danmaku-insight .

# 需要 NVIDIA GPU + nvidia-docker
docker run --gpus all -p 8000:8000 \
  -v ./output:/app/output \
  -v ./config:/app/config \
  danmaku-insight
```

首次启动会自动从 HuggingFace 镜像站下载 Qwen3-0.6B（约 1.2GB），之后通过 volume 缓存不再重复下载。

### 方式 C：模型预装（镜像自包含，拿来即用）

```bash
# 构建时打包模型（镜像约 +1.2GB，但启动即用）
docker build --build-arg PRELOAD_MODEL=1 -t danmaku-insight:full .

docker run --gpus all -p 8000:8000 \
  -v ./output:/app/output \
  -v ./config:/app/config \
  danmaku-insight:full
```

### 使用 docker-compose

```bash
# 本地模型（含 GPU 配置）
docker compose up

# 走云端 API：先按上面方式 A 写好 config/llm.json，并删掉 compose 文件里的 deploy 段
export LLM_PROVIDER=openai
docker compose up -d
```

密钥只放在 `config/llm.json`（已被 `.gitignore` 和 `.dockerignore` 排除），
不要写进 `docker-compose.yml`，也不要用 `-e` 传。

### 前提条件

- Docker 20.10+
- 以下仅本地模型（`LLM_PROVIDER=local`）需要：
  - [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) (nvidia-docker)
  - NVIDIA GPU（Qwen3-0.6B 需约 1.1GB 显存）

## 评论采集限制

未登录时评论接口只返回**降级响应**：无论评论区实际有多少条，一律只给 3 条根评论。
实测三个视频，`sort=1`（热度）都只回 3 条，`sort=0`（时间）回 0 条：

| 视频 | 评论区总数 | `sort=1` | `sort=0` |
|------|-----------|----------|----------|
| BV1xx411c7mD | 89044 | 3 条 | 0 条 |
| BV1G48M6XEBt | 19176 | 3 条 | 0 条 |
| BV1yj8T6zE1N | 23203 | 3 条 | 0 条 |

换排序、去掉 `nohot` 参数都无效 —— 这不是排序策略问题，要拿到完整评论**必须带登录态**：

```bash
# 浏览器登录 B站 → 开发者工具 → Application → Cookies → 复制 SESSDATA
export BILIBILI_SESSDATA=你的SESSDATA值
python fetch_video.py BV117411r7R1 --max-comments 500
```

`SESSDATA` 是账号凭据，只用环境变量传入，不要写进代码或提交到仓库。

子评论不受此限制，未登录也能正常拉取（上面第一个视频拿到了 2814 条），所以
不带登录态时分析仍能跑，只是样本以子评论为主、缺少高赞根评论。

## 注意事项

- 用本地模型时首次运行会从 HuggingFace 下载 Qwen3-0.6B（约 1.2GB），国内环境需设置
  `export HF_ENDPOINT=https://hf-mirror.com`；走云端 API 则无需下载，也不必安装 torch
- 本服务没有鉴权，模型配置接口默认只接受本机请求，详见上文「关于密钥安全」
- 弹幕接口有实时池上限（约 1200 条），历史弹幕需登录态
- 评论采集需登录态才能拿到完整数据，详见上文「评论采集限制」
