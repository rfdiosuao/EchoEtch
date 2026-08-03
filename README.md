<p align="center">
  <img src="docs/logo.jpg" alt="聲畫合鳴 EchoEtch Logo" width="160">
</p>

<h1 align="center">聲畫合鳴 EchoEtch</h1>

<p align="center">
  随手记录此刻 —— AI 将你的文字、照片、语音转译为冥想式叙事，合成治愈系语音，沉淀为情绪日记。
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-3.0+-black?logo=flask&logoColor=white">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Web%20%7C%20Mobile-green?logo=googlechrome&logoColor=white">
  <img alt="Demo Mode" src="https://img.shields.io/badge/Demo%20Mode-No%20API%20Key%20Needed-orange">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow">
</p>

<p align="center">
  <a href="https://sshm.heang.top">在线演示</a> · <a href="https://sshm.heang.top/preview">路演预览</a> · <a href="ARCHITECTURE.md">架构文档</a> · <a href="《聲畫合鳴》完整产品需求分析书（PRD）.md">产品需求文档</a>
</p>

---

## 这是什么

聲畫合鳴（Echo & Etch）是一款**情绪记录与疗愈**应用。它不要求你写完美的日记，只需随手留下一个痕迹——几个字、一张照片、一段语音——AI 会将它转译为一段 100-150 字的冥想式叙事，并合成温柔的人声音频，最终沉淀为你的「回声日记」。

### 核心价值链

```
用户随手记录（文字 / 照片 / 语音）
        ↓
   AI 叙事转译（LLM 生成冥想式文本）
        ↓
   语音合成（TTS 治愈系音频）
        ↓
   回声卡片（叙事文本 + 音频播放 + 归档）
        ↓
   情绪日记（日历视图 + 历史回放）
```

### 与同类产品的区别

| 维度 | 普通日记 App | 聲畫合鳴 |
|------|-------------|---------|
| 输入门槛 | 需要写完整段落 | 几个字、一张照片、一段语音即可 |
| 输出形态 | 你写的原文 | AI 转译的冥想式叙事 + 语音 |
| 情绪价值 | 记录 | 被听见、被回应 |
| 回看体验 | 文字列表 | 日历 + 音频回放 |

---

## 功能一览

| 功能 | 状态 | 说明 |
|------|:----:|------|
| 每日主题 | ✅ | 10 种主题轮换（情绪觉察 / 细节捕捉 / 感恩回顾等） |
| 文字输入 | ✅ | 最多 20,000 字；长文本走后台分段生成与合并 |
| 拍照 / 涂鸦 | ✅ | 识别画面生成叙事，并保留用户原图 |
| 语音输入 | ✅ | Whisper 语音转文字 → 叙事生成 |
| AI 叙事生成 | ✅ | LLM 生成 100-150 字冥想式文本 |
| AI 图片生成 | ✅ | 独立 OpenAI 兼容接口；未配置时保留原图或跳过生图 |
| TTS 语音合成 | ✅ | 小米 MiMo 公共 API，支持长文本分段合成为本地 WAV |
| 回声卡片 | ✅ | 叙事展示 + 音频播放 |
| 回声日记 | ✅ | 日历视图 + 按日浏览历史记录 |
| Demo 模式 | ✅ | 无需任何 API Key 即可体验完整流程 |

> **Demo 模式**：未配置 API Key 时，LLM 返回预设叙事、语音识别返回占位文本、TTS 跳过音频生成。所有功能模块均可正常演示。

---

## 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装与运行

```bash
# 1. 克隆仓库
git clone https://github.com/rfdiosuao/EchoEtch.git
cd EchoEtch

# 2. 安装依赖
pip install -r demo/backend/requirements.txt

# 3. 启动服务
python demo/backend/app.py
```

打开浏览器访问 **http://localhost:8721** 即可。

> 手机访问：将 `localhost` 替换为电脑局域网 IP，如 `http://192.168.x.x:8721`

### 运行测试

```bash
python -m unittest discover -s demo/backend -p "test*.py" -v
```

### macOS / Linux 一键启动

```bash
cd EchoEtch/demo
chmod +x start.sh
./start.sh
```

---

## 配置 API Key（可选）

项目默认运行 **Demo 模式**，无需任何 Key。如需真实 AI 生成，复制配置模板并填入真实值：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# ---- LLM 大语言模型（叙事生成 + 图片理解）----
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen2-VL-72B-Instruct
OPENAI_MODEL_TEXT=Qwen/Qwen2.5-72B-Instruct

# ---- 语音识别 Whisper ----
WHISPER_URL=https://api.siliconflow.cn/v1
WHISPER_API_KEY=sk-your-key
WHISPER_MODEL=FunAudioLLM/SenseVoiceSmall

# ---- 独立图片生成（可选）----
IMAGE_API_KEY=sk-your-key
IMAGE_BASE_URL=https://api.heang.top/v1
IMAGE_MODEL=gpt-image-2

# ---- TTS 语音合成（小米 MiMo 公共 API）----
MIMO_TTS_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_TTS_API_KEY=sk-your-key
MIMO_TTS_MODEL=mimo-v2.5-tts
MIMO_TTS_VOICE=茉莉                    # 可选: mimo_default, 冰糖, 茉莉, 苏打, 白桦, Mia, Chloe, Milo, Dean
MIMO_TTS_TIMEOUT=120
```

| 配置项 | 用途 | 未配置时 |
|--------|------|---------|
| `OPENAI_API_KEY` | LLM 叙事生成 + 视觉模型 | Demo 模式，返回预设叙事 |
| `WHISPER_API_KEY` | 语音转文字 | 返回占位文本 `[语音录入]` |
| `IMAGE_API_KEY` | 根据叙事或参考图生成插画 | 保留原始图片或跳过生图 |
| `MIMO_TTS_API_KEY` | TTS 音频合成（小米 MiMo） | 跳过音频，仅展示文字 |

> **推荐**：[硅基流动 SiliconFlow](https://siliconflow.cn) 提供 OpenAI 兼容接口，国内可用，免费额度覆盖 Qwen 系列模型。

---

## 项目结构

```
EchoEtch/
├── demo/
│   ├── backend/
│   │   ├── app.py              # Flask 后端（单文件，含全部路由和业务逻辑）
│   │   ├── requirements.txt    # Python 依赖
│   │   └── test_app.py         # MiMo TTS 与上游流程回归测试
│   ├── frontend/
│   │   ├── index.html          # 前端页面（移动端优先，原生 HTML/CSS/JS）
│   │   └── tailwind.min.js     # Tailwind CSS（本地引入）
│   ├── data/
│   │   ├── diary.json          # 回声日记数据（JSON 文件存储）
│   │   ├── audio/              # TTS 生成的音频文件（不提交）
│   │   └── images/             # 上传及生成的图片（不提交）
│   └── start.sh                # macOS / Linux 启动脚本
├── .env.example                # 环境变量模板
├── .gitignore
├── ARCHITECTURE.md             # 完整架构设计文档（Demo → 生产级蓝图）
├── EchoEtch简介及路演preview.html  # 路演演示页面
└── 《聲畫合鳴》完整产品需求分析书（PRD）.md
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Flask 3.0+ | 单文件，JSON 文件存储，无数据库 |
| 前端 | HTML / CSS / JS | 移动端优先，Tailwind CSS |
| LLM | Qwen2-VL-72B / Qwen2.5-72B | 通过 SiliconFlow OpenAI 兼容接口调用 |
| 语音识别 | Whisper (SenseVoice) | SiliconFlow 平台，中文优化 |
| 图片生成 | OpenAI 兼容 Images API | 与叙事模型密钥独立配置 |
| 语音合成 | 小米 MiMo TTS | 小米公共 API，温柔女声音色 |
| 配置管理 | python-dotenv | 从 `.env` 文件加载环境变量 |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 后端配置状态（Demo 模式检测） |
| `GET` | `/api/theme/today` | 获取今日主题 |
| `POST` | `/api/echo/generate` | 生成回声（文字 / 图片 / 涂鸦） |
| `POST` | `/api/echo/voice` | 语音输入 → 转文字 → 生成叙事 |
| `GET` | `/api/echo/jobs/{job_id}` | 查询长文本后台任务状态 |
| `GET` | `/api/audio/{filename}` | 读取生成的 TTS 音频 |
| `GET` | `/api/images/{filename}` | 读取上传或生成的图片 |
| `GET` | `/api/diary` | 获取全部日记（按日期倒序） |
| `GET` | `/api/diary/{date}` | 获取指定日期的回声 |
| `GET` | `/preview` | 路演演示页面 |

### 请求示例

```bash
# 文字输入
curl -X POST http://localhost:8721/api/echo/generate \
  -H "Content-Type: application/json" \
  -d '{"type": "text", "content": "今天看到一片很好看的云", "theme": "细节捕捉"}'

# 语音输入
curl -X POST http://localhost:8721/api/echo/voice \
  -F "file=@voice.webm" \
  -F "theme=情绪觉察"
```

---

## 架构设计

当前为 **Demo 阶段**（Flask + JSON 存储），完整生产级架构设计见 [ARCHITECTURE.md](ARCHITECTURE.md)，包含：

- **FastAPI + Vue 3** 架构重构方案
- **豆包 TTS V3** 流式 WebSocket 推送（首包 < 500ms）
- **PostgreSQL + Redis** 数据层
- **三层缓存** TTS 策略
- **Docker Compose** 部署方案
- **安全合规** 设计（JWT / 内容过滤 / 速率限制）

```
当前 Demo                    生产级目标
───────────                 ───────────
Flask + JSON    ──→         FastAPI + PostgreSQL + Redis
MiMo TTS / 本地 WAV ──→       豆包 V3 流式 TTS (WebSocket)
单文件 HTML     ──→         Vue 3 SPA + 组件化
无认证          ──→         JWT Bearer Token
debug=True     ──→         Nginx + waitress 生产部署
```

---

## 开发路线图

| 阶段 | 目标 | 状态 |
|------|------|:----:|
| **Demo** | 功能可演示，Demo 模式无需 Key | ✅ 完成 |
| **Phase 0** | 安全修复（关闭 debug、CORS 白名单、XSS 修复） | 📋 规划中 |
| **Phase 1** | FastAPI + Vue 3 + 豆包流式 TTS | 📋 规划中 |
| **Phase 2** | 体验深化（LLM 流式 SSE、多音色、PWA） | 📋 规划中 |
| **Phase 3** | 分层适配（青少年模式 / 老年简化模式） | 📋 规划中 |

---

## 贡献

欢迎提交 Issue 和 Pull Request。

```bash
# 开发流程
git checkout -b feature/your-feature
# 做修改...
git commit -m "feat: 描述你的改动"
git push origin feature/your-feature
# 在 GitHub 上创建 Pull Request
```

---

## 许可证

MIT License — 自由使用、修改、分发。

---

> **聲畫合鳴** — 让每一个此刻，都被温柔地听见。
