# 弹幕评论区智能分析

输入一个 B 站 BV 号，自动抓取弹幕和评论，生成一份可视化的观众复盘报告。

## 这套系统能做什么

- 🔍 **抓取视频信息**：标题、UP 主、封面、播放量、弹幕数、评论数
- 🧹 **清洗去重**：规则过滤 + LLM 辅助识别刷屏、灌水和噪声内容
- 📊 **主题聚类**：对弹幕和评论做 TF-IDF + KMeans 聚类
- ⏱️ **高能时刻识别**：找出弹幕密度峰值区间
- 🤖 **LLM 归纳**：生成弹幕主题名、评论主题、争议判断、复盘结论和改进建议
- 🌈 **词云展示**：分别展示弹幕词云和评论词云
- 🧭 **洞察导航**：按「弹幕反馈 / 高能时刻 / 评论总结 / 复盘报告」下钻查看
- 📝 **Markdown 导出**：一键导出完整复盘报告
- 🌐 **Web 实时进度**：SSE 流式显示采集、清洗、聚类和报告生成过程

## 当前界面长什么样

Web 页面已经拆成独立前端目录，不再使用单个大 HTML 文件：

- `frontend/index.html`：页面结构
- `frontend/styles/base.css`：全局样式
- `frontend/styles/drill.css`：下钻详情样式
- `frontend/scripts/`：按功能拆分的前端脚本

后端会把 `frontend/` 挂载为静态资源，并在 `/` 返回首页。

## 快速开始

### 1）安装依赖

```bash
pip install -r requirements.txt
```

### 2）配置 LLM

当前代码支持两个后端：

- `openai`：任意 OpenAI 兼容接口
- `anthropic`：Anthropic Messages API

> 目前**不支持 local 本地模型后端**。如果你看到旧文档里写了 local，以当前代码为准。

优先级是：**配置文件 > 环境变量 > 默认值**。

推荐直接写 `config/llm.json`：

#### OpenAI 兼容接口示例

```bash
mkdir -p config
cat > config/llm.json <<'JSON'
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
```

#### Anthropic 示例

```bash
mkdir -p config
cat > config/llm.json <<'JSON'
{
  "provider": "anthropic",
  "anthropic": {
    "model": "claude-opus-5",
    "api_key": "sk-ant-xxx",
    "base_url": "https://api.anthropic.com"
  }
}
JSON
chmod 600 config/llm.json
```

### 3）启动 Web 服务

```bash
python server.py
```

打开：`http://localhost:8000`

### 4）输入 BV 号开始分析

支持直接输入 BV 号或视频链接。页面会实时显示：

- 当前步骤
- 分析进度
- 词云和主题结果
- 复盘结论和改进建议

## 也可以直接用命令行

### 采集数据

```bash
python fetch_video.py BV1xx411c7mD
```

常用参数：

```bash
python fetch_video.py BV1xx411c7mD \
  --max-comments 200 \
  --output-dir ./output \
  --delay 0.3 \
  --comment-sort 1
```

参数说明：

- `--max-comments`：最多采集多少条根评论，默认 500
- `--output-dir`：输出目录，默认 `./output`
- `--delay`：请求间隔，默认 0.3 秒
- `--skip-danmaku`：跳过弹幕采集
- `--skip-comments`：跳过评论采集
- `--comment-sort`：评论排序，`0=按时间`，`1=按热度`

### 分析已采集数据

```bash
python analyze_video.py BV1xx411c7mD
```

也可以直接传数据目录：

```bash
python analyze_video.py ./output/BV1xx411c7mD/
```

常用参数：

- `--provider`：`openai` / `anthropic`
- `--model`：覆盖模型名
- `--api-key`：覆盖 API Key
- `--base-url`：覆盖接口地址
- `--output-dir`：数据根目录，默认 `./output`
- `--skip-clean`：跳过清洗步骤

## Web API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| GET | `/` | Web 界面 |
| GET | `/api/analyze/stream?bvid=xxx&force=true` | SSE 流式分析（采集 + 清洗 + 聚类 + 报告） |
| GET | `/api/report/{bvid}` | 获取已生成的缓存报告 |

### SSE 事件

`/api/analyze/stream` 会推送三类事件：

- `progress`：进度更新
- `done`：最终报告 JSON
- `error`：失败信息

如果同一个 BV 已经有 `report.json`，默认会直接复用缓存；加 `force=true` 可以强制重跑。

## 输出结构

```text
output/{BV号}/
├── video_info.json   视频元信息
├── danmaku.json      弹幕原始数据
├── comments.json     评论原始数据
└── report.json       分析报告
```

### report.json 主要字段

```json
{
  "video": {
    "title": "",
    "up": "",
    "play": "",
    "dm": 0,
    "cm": 0,
    "bvid": "",
    "cover": "",
    "duration": 0
  },
  "dmThemes": [{ "n": "", "c": 0, "t": "" }],
  "peaks": [{ "tm": "", "x": "", "n": 0, "s": "" }],
  "cmThemes": [{
    "n": "",
    "c": 0,
    "pct": 0,
    "dis": "",
    "q": [{ "t": "", "l": 0, "r": 0, "k": "pro", "why": [] }],
    "note": ""
  }],
  "slots": [{ "h": "", "p": "", "r": "", "refs": [] }],
  "acts": [{ "t": "", "s": "" }],
  "wordcloud": { "dm": [], "cm": [] },
  "wordClouds": { "dm": [], "cm": [] },
  "logs": [],
  "meta": {
    "provider": "",
    "model": "",
    "backend": "",
    "elapsed": 0,
    "clean_stats": {}
  }
}
```

## 模型配置说明

### 配置文件

默认读取：`./config/llm.json`

也可以通过环境变量改路径：

```bash
export LLM_CONFIG_PATH=/path/to/llm.json
```

### 支持的环境变量

| 变量 | 说明 |
| ---- | ---- |
| `LLM_PROVIDER` | 后端选择：`openai` / `anthropic` |
| `LLM_MODEL` | 模型名 |
| `BSTAR_KEY` | API Key |
| `BSTAR_MODEL` | 模型名，优先级高于 `LLM_MODEL` |
| `BSTAR_BASE_URL` | 接口地址 |
| `LLM_CONFIG_PATH` | 配置文件路径 |

注意：当前项目没有暴露 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 之类的环境变量入口，密钥请放在 `config/llm.json` 或使用上面的 `BSTAR_KEY`。

## 项目结构

```text
.
├── server.py
├── fetch_video.py
├── analyze_video.py
├── frontend/
│   ├── index.html
│   ├── styles/
│   └── scripts/
├── bilibili/
├── analysis/
├── config/
├── output/
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```

## 技术栈

- **采集**：requests + B 站公开接口
- **分析**：jieba + scikit-learn + LLM
- **后端**：FastAPI + SSE
- **前端**：原生 HTML / CSS / JS

## Docker 部署

### 构建并运行

```bash
docker build -t danmaku-insight .

docker run -p 8000:8000 \
  -v ./output:/app/output \
  -v ./config:/app/config \
  -e LLM_PROVIDER=anthropic \
  danmaku-insight
```

### docker compose

```bash
docker compose up --build
```

## 一些说明

- 网页模式默认为了速度，会限制采集评论数量；CLI 可以通过 `--max-comments` 调大。
- 页面上的“重新演示”会回到输入页，方便反复试不同 BV。
- Markdown 导出内容来自当前报告 JSON，可直接保存或二次编辑。
- 旧的单文件前端已经拆分为 `frontend/`，便于维护和扩展。

## 许可

如项目未另行说明，按仓库当前约定使用。
