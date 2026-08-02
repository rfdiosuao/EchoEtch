from __future__ import annotations
"""
《聲畫合鳴》Echo & Etch - 后端 v2
完整版：支持图片识别 + 语音转文字 + LLM生成 + TTS

依赖安装：
  pip install flask flask-cors python-dotenv requests Pillow

API Key 配置（任选一种）：
  1. 硅基流动（国内，推荐）：https://siliconflow.cn
  2. OpenAI API（需要代理）
  3. 其他 OpenAI 兼容接口

环境变量设置：
  export OPENAI_API_KEY="sk-xxx"
  export OPENAI_BASE_URL="https://api.siliconflow.cn/v1"   # 硅基流动
  export OPENAI_MODEL="Qwen/Qwen2-VL-72B-Instruct"          # 视觉模型（支持图片理解）
  export OPENAI_MODEL_TEXT="Qwen/Qwen2.5-72B-Instruct"       # 文本模型
  export WHISPER_URL="https://api.siliconflow.cn/v1"        # Whisper API（硅基流动）
  export WHISPER_API_KEY="sk-xxx"
  export DOBAO_TTS_URL="https://db.heang.top"               # db.heang.top TTS 接口地址
  export DOBAO_TTS_USER="heang"                              # TTS 用户名
  export DOBAO_TTS_PASSWORD=""                               # TTS 密码（必填，否则 TTS 不可用）
  export DOBAO_TTS_VOICE="zh_female_wenroutaozi_uranus_bigtts"  # TTS 音色
"""

import os
import io
import json
import uuid
import base64
import datetime
from pathlib import Path

# 加载 .env 文件（优先级：系统环境变量 > .env 文件）
try:
    from dotenv import load_dotenv
    # 依次尝试从 backend/、demo/、项目根目录加载 .env
    for env_path in [Path(__file__).parent / ".env",
                     Path(__file__).parent.parent / ".env",
                     Path(__file__).parent.parent.parent / ".env"]:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            print(f"[配置] 已加载: {env_path}")
            break
    else:
        print("[配置] 未找到 .env 文件，将使用系统环境变量")
except ImportError:
    print("[配置] python-dotenv 未安装，将使用系统环境变量")

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
from PIL import Image

app = Flask(__name__)
CORS(app)

# ========================
# 配置区
# ========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_VISION = os.getenv("OPENAI_MODEL", "Qwen/Qwen2-VL-72B-Instruct")
MODEL_TEXT = os.getenv("OPENAI_MODEL_TEXT", "Qwen/Qwen2.5-72B-Instruct")
WHISPER_URL = os.getenv("WHISPER_URL", "https://api.siliconflow.cn/v1")
WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "") or OPENAI_API_KEY

# db.heang.top TTS 配置
DOBAO_TTS_URL = os.getenv("DOBAO_TTS_URL", "https://db.heang.top")
DOBAO_TTS_USER = os.getenv("DOBAO_TTS_USER", "heang")
DOBAO_TTS_PASSWORD = os.getenv("DOBAO_TTS_PASSWORD", "")
DOBAO_TTS_VOICE = os.getenv("DOBAO_TTS_VOICE", "zh_female_wenroutaozi_uranus_bigtts")

# 启动时打印配置状态
print("=" * 50)
print("《聲畫合鳴》v2 - 完整版（含图片识别+语音转文字）")
print("=" * 50)
_demo = not (OPENAI_API_KEY and WHISPER_API_KEY and DOBAO_TTS_PASSWORD)
if _demo:
    print(f"⚠ LLM: {'已配置' if OPENAI_API_KEY else '未配置 API Key，运行 Demo 模式'}")
    print(f"⚠ Whisper: {'已配置' if WHISPER_API_KEY else '未配置 API Key，语音识别用占位文本'}")
    print(f"✗ TTS: {'已配置' if DOBAO_TTS_PASSWORD else '未配置 DOBAO_TTS_PASSWORD，音频不可用'}")
else:
    print("✓ LLM: 已配置")
    print("✓ Whisper: 已配置")
    print("✓ TTS: 已配置")
    print("访问地址：http://localhost:8721")

# 数据存储
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
DIARY_FILE = DATA_DIR / "diary.json"


def load_diary():
    return json.loads(DIARY_FILE.read_text(encoding="utf-8")) if DIARY_FILE.exists() else {}


def save_diary(diary):
    DIARY_FILE.write_text(json.dumps(diary, ensure_ascii=False, indent=2), encoding="utf-8")

def dedup_diary(diary):
    """对每天的记录按 narrative 去重，保留第一条"""
    for date, items in diary.items():
        seen = set()
        unique = []
        for item in items:
            nar = item.get("narrative", "")
            if nar in seen:
                continue
            seen.add(nar)
            unique.append(item)
        diary[date] = unique
    return diary


# ========================
# 每日主题
# ========================
DAILY_THEMES = [
    {"type": "情绪觉察", "text": "此刻你最想对自己说的一句话是什么？"},
    {"type": "细节捕捉", "text": "今天最让你意外的一个瞬间是什么？"},
    {"type": "感恩回顾", "text": "一个你想感谢但没说出口的人，是谁？"},
    {"type": "身体感知", "text": "此刻你身体的哪个部位最紧绷？"},
    {"type": "未来对话", "text": "给一个月后的自己留一句话。"},
    {"type": "自由记录", "text": "今天有什么想被听见的？"},
    {"type": "情绪觉察", "text": "如果今天是一首歌，它是什么颜色？"},
    {"type": "细节捕捉", "text": "今天窗外你看到了什么？"},
    {"type": "感恩回顾", "text": "最近一次让你笑出声的事是什么？"},
    {"type": "身体感知", "text": "今晚躺在床上，你最先感受到的是什么？"},
]


def get_today_theme():
    day_of_year = datetime.date.today().timetuple().tm_yday
    theme = DAILY_THEMES[day_of_year % len(DAILY_THEMES)]
    return {"date": str(datetime.date.today()), "type": theme["type"], "text": theme["text"]}


# ========================
# LLM 统一调用
# ========================
def llm_chat(messages, model=None, temperature=0.8, max_tokens=400):
    """通用 LLM 调用，支持 OpenAI 兼容接口"""
    if not OPENAI_API_KEY:
        return None, "未配置 API Key"

    target_model = model or MODEL_TEXT
    try:
        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": target_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip(), None
    except Exception as e:
        return None, str(e)


def llm_vision(image_data: bytes, prompt: str):
    """视觉模型：分析图片内容"""
    if not OPENAI_API_KEY:
        return None, "未配置 API Key"

    # 图片 base64 编码
    img_b64 = base64.b64encode(image_data).decode()

    # 判断模型类型
    model = MODEL_VISION
    is_qwen_vl = "Qwen" in model and "VL" in model

    try:
        if is_qwen_vl:
            # Qwen VL 格式
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
        else:
            # OpenAI GPT-4V 格式
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]

        resp = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": 512, "temperature": 0.7},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip(), None
    except Exception as e:
        return None, str(e)


# ========================
# 图片理解 + 叙事生成（核心流程）
# ========================
VISION_PROMPT = """你是一位温暖、细腻的倾听者。请仔细观察这张图片，描述你看到的内容（可以是物体、场景、文字、情绪氛围等），用2-3句话描述你感受到的画面。"""


NARRATIVE_PROMPT = """你是一位温暖、细腻的倾听者与陪伴者。

任务：基于用户提供的素材，生成一段约100-150字的冥想式叙事。

素材可能是：
- 用户随手写下的文字
- 用户拍下的一张照片描述
- 用户说的一段话
- 或者只是几个字、一种感觉

原则：
1. 不纠正、不挑剔素材的"不完美"，从中提取有温度的元素
2. 语气温柔、平静，像深夜电台的独白或写给自己的信
3. 不加标题、解释或评价，直接输出叙事文本
4. 关注"此刻"，帮助用户停留在当下

素材：{user_input}

叙事文本："""


def generate_narrative(user_input: str) -> str:
    """生成冥想式叙事"""
    # Demo 模式
    if not OPENAI_API_KEY:
        demo = [
            "今天你留下的痕迹里，有光。今天的忙碌没有把你淹没，你还在这里，还在感受，还在记录。这就是你对自己的温柔。回声已生成，它会等你，直到你想听的时候。",
            "有些话，说给自己听，比说给全世界听更重要。你选择在这里留下痕迹，这就是你对自己的温柔。无论今天发生了什么，此刻，你是安全的。",
            "你留下的每一个痕迹，都是给自己的礼物。不必完美，不必精彩，只需要真实。AI听见了它们，把它们变成回声--属于你的，独一无二的回声。",
        ]
        import random
        return random.choice(demo)

    prompt = NARRATIVE_PROMPT.format(user_input=user_input)
    result, err = llm_chat([{"role": "user", "content": prompt}], temperature=0.85, max_tokens=300)
    if err:
        return f"今天的你，值得被自己听见。{user_input}"
    return result


def process_image(image_data: bytes) -> str:
    """处理图片：视觉理解 -> 叙事"""
    if not OPENAI_API_KEY:
        return "照片里的光影，像是你给自己的礼物。今天有什么被记录下来了？"

    # Step 1: 图片内容理解
    desc, err = llm_vision(image_data, VISION_PROMPT)
    if err or not desc:
        desc = "这张照片里有你记录的一个瞬间"

    # Step 2: 基于描述生成叙事
    narrative = generate_narrative(f"用户拍了这张照片：{desc}")
    return narrative


# ========================
# 语音转文字（Whisper）
# ========================
def transcribe_audio(audio_data: bytes, filename="voice.webm") -> str:
    """Whisper 语音转文字（Demo 模式下返回占位文本）"""
    if not WHISPER_API_KEY:
        # Demo 模式：返回占位文本，让语音功能可用
        print("[Whisper] 未配置 API Key，使用 Demo 模式")
        return "[语音录入] 这是你刚才说的话，回声已为你生成"

    try:
        # 构建文件
        files = {"file": (filename, io.BytesIO(audio_data), "audio/webm")}
        data = {"model": "SenseVoice", "language": "zh"}
        headers = {"Authorization": f"Bearer {WHISPER_API_KEY}"}

        resp = requests.post(
            f"{WHISPER_URL}/audio/transcriptions",
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()
    except Exception as e:
        print(f"[Whisper 失败] {e}")
        # Whisper 失败时也返回占位文本，不让整个流程中断
        return "[语音录入] 这是你刚才说的话，回声已为你生成"


# ========================
# TTS 音频生成
# ========================
def generate_tts(text: str) -> str | None:
    """调用 db.heang.top 生成 TTS 音频，返回公开 MP3 URL"""
    if not DOBAO_TTS_PASSWORD:
        print("[TTS] 未配置 DOBAO_TTS_PASSWORD，跳过 TTS 生成")
        return None

    try:
        import base64
        auth = base64.b64encode(f"{DOBAO_TTS_USER}:{DOBAO_TTS_PASSWORD}".encode()).decode()
        resp = requests.post(
            f"{DOBAO_TTS_URL}/api/tts",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "speaker": DOBAO_TTS_VOICE,
                "rate": 0,
                "pitch": 0,
            },
            timeout=30,  # 从 180s 降到 30s，避免前端超时
        )
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        audio_url = data.get("storageUrl") or data.get("url") or data.get("local_url")
        if audio_url and audio_url.startswith("/"):
            audio_url = f"{DOBAO_TTS_URL}{audio_url}"
        return audio_url
    except Exception as e:
        print(f"[TTS 失败] {e}")
        return None


# ========================
# API 路由
# ========================
@app.route("/")
def index():
    return send_from_directory(BASE_DIR / "frontend", "index.html")


@app.route("/preview")
def preview():
    """路演演示页"""
    preview_file = BASE_DIR.parent / "EchoEtch简介及路演preview.html"
    if preview_file.exists():
        return send_from_directory(preview_file.parent, preview_file.name)
    return send_from_directory(BASE_DIR / "frontend", "index.html")


@app.route("/frontend/<path:filename>")
def frontend_files(filename):
    """服务前端静态文件"""
    return send_from_directory(BASE_DIR / "frontend", filename)


@app.route("/api/status")
def api_status():
    """返回后端运行状态（供前端检测 Demo 模式）"""
    demo_mode = not OPENAI_API_KEY or not WHISPER_API_KEY
    return jsonify({
        "demo_mode": demo_mode,
        "has_api_key": bool(OPENAI_API_KEY),
        "has_whisper": bool(WHISPER_API_KEY),
        "has_tts": bool(DOBAO_TTS_PASSWORD),
        "message": "Demo 模式：语音识别和 TTS 使用占位文本" if demo_mode else "正常模式",
    })


@app.route("/api/config")
def api_config():
    """返回当前配置状态"""
    return jsonify({
        "has_api_key": bool(OPENAI_API_KEY),
        "has_whisper": bool(WHISPER_API_KEY),
        "model_vision": MODEL_VISION if OPENAI_API_KEY else None,
        "model_text": MODEL_TEXT if OPENAI_API_KEY else None,
    })


@app.route("/api/theme/today")
def api_theme():
    return jsonify(get_today_theme())


@app.route("/api/echo/generate", methods=["POST"])
def api_generate():
    """
    生成回声
    支持三种输入：
    1. text: 文字直接输入
    2. image / doodle: 图片或涂鸦（base64），自动识别 + 生成叙事
    3. voice: 语音（binary），自动转文字 + 生成叙事
    """
    data = request.get_json() or {}
    input_type = data.get("type", "text")
    theme = data.get("theme", "")

    # ---- 文字输入 ----
    if input_type == "text":
        user_content = data.get("content", "").strip()
        if not user_content:
            return jsonify({"error": "内容不能为空"}), 400
        narrative = generate_narrative(user_content)

    # ---- 图片 / 涂鸦输入 ----
    elif input_type in ("image", "doodle"):
        img_b64 = data.get("content", "")  # base64 字符串
        if not img_b64:
            return jsonify({"error": "图片或涂鸦不能为空"}), 400
        try:
            # 浏览器 FileReader/canvas 导出的内容是 data:image/...;base64,...
            # 去掉前缀后再严格解码，避免把 MIME 元数据当作图像字节。
            if img_b64.startswith("data:"):
                img_b64 = img_b64.split(",", 1)[1]
            image_data = base64.b64decode(img_b64, validate=True)
        except Exception:
            return jsonify({"error": "图片或涂鸦格式错误"}), 400
        narrative = process_image(image_data)

    # ---- 语音输入 ----
    elif input_type == "voice":
        # 语音走 form-data 传输
        return jsonify({"error": "请使用 /api/echo/voice 接口上传语音"}), 400

    else:
        return jsonify({"error": f"不支持的类型: {input_type}"}), 400

    # 生成音频
    echo_id = uuid.uuid4().hex[:8]
    audio_url = generate_tts(narrative)

    # 保存日记
    diary = load_diary()
    today = str(datetime.date.today())
    diary.setdefault(today, [])
    record = {
        "id": echo_id,
        "theme": theme,
        "user_input": data.get("content", ""),
        "input_type": input_type,
        "narrative": narrative,
        "audio_url": audio_url,
        "created_at": datetime.datetime.now().isoformat(),
    }
    diary[today].append(record)
    dedup_diary(diary)
    save_diary(diary)

    return jsonify({
        "id": echo_id,
        "narrative": narrative,
        "audio_url": audio_url,
        "date": today,
    })


@app.route("/api/echo/voice", methods=["POST"])
def api_echo_voice():
    """语音输入 -> Whisper转文字 -> AI叙事 -> TTS音频"""
    if "file" not in request.files:
        return jsonify({"error": "需要上传音频文件"}), 400

    audio_file = request.files["file"]
    audio_data = audio_file.read()
    theme = request.form.get("theme", "")

    # Step 1: Whisper 转文字（Demo 模式会返回占位文本）
    transcribed = transcribe_audio(audio_data, audio_file.filename or "voice.webm")
    if not transcribed:
        transcribed = "[语音录入] 这是你刚才说的话"

    # Step 2: AI 生成叙事
    narrative = generate_narrative(f"用户语音输入：{transcribed}")

    # Step 3: TTS 生成音频（可能为 None，不影响主体流程）
    echo_id = uuid.uuid4().hex[:8]
    try:
        audio_url = generate_tts(narrative)
    except Exception as e:
        print(f"[TTS 异常] {e}")
        audio_url = None

    # 保存
    diary = load_diary()
    today = str(datetime.date.today())
    diary.setdefault(today, [])
    diary[today].append({
        "id": echo_id,
        "theme": theme,
        "user_input": transcribed,
        "input_type": "voice",
        "narrative": narrative,
        "audio_url": audio_url,
        "created_at": datetime.datetime.now().isoformat(),
    })
    dedup_diary(diary)
    save_diary(diary)

    return jsonify({
        "id": echo_id,
        "transcribed": transcribed,
        "narrative": narrative,
        "audio_url": audio_url,
        "date": today,
    })


@app.route("/api/audio/<filename>")
def api_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/api/diary")
def api_diary():
    diary = dedup_diary(load_diary())
    return jsonify(dict(sorted(diary.items(), reverse=True)))


@app.route("/api/diary/<date>")
def api_diary_date(date):
    diary = load_diary()
    return jsonify({"date": date, "echoes": diary.get(date, [])})


# ========================
# 启动
# ========================
if __name__ == "__main__":
    print("=" * 44)
    print("《聲畫合鳴》v2 - 完整版（含图片识别+语音转文字）")
    print("=" * 44)
    if OPENAI_API_KEY:
        print(f"✓ LLM: {OPENAI_BASE_URL}")
        print(f"✓ 视觉模型: {MODEL_VISION}")
        print(f"✓ 文本模型: {MODEL_TEXT}")
        if WHISPER_API_KEY:
            print(f"✓ Whisper: 已配置")
        else:
            print("✗ Whisper: 未配置（语音转文字不可用）")
    else:
        print("⚠ LLM: 未配置 API Key，运行 Demo 模式")
    if DOBAO_TTS_PASSWORD:
        print(f"✓ TTS: {DOBAO_TTS_URL} (音色: {DOBAO_TTS_VOICE})")
    else:
        print("✗ TTS: 未配置 DOBAO_TTS_PASSWORD")
    print(f"访问地址：http://localhost:8721")
    print("=" * 44)
    app.run(host="0.0.0.0", port=8721, debug=True)
