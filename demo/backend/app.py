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
import hashlib
import datetime
import re
import subprocess
import threading
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
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "FunAudioLLM/SenseVoiceSmall")

# 独立的生图接口配置（不复用 LLM 密钥，避免影响现有叙事/语音链路）
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://api.heang.top/v1").rstrip("/")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-2")

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
IMAGE_DIR = DATA_DIR / "images"
IMAGE_DIR.mkdir(exist_ok=True)
DIARY_FILE = DATA_DIR / "diary.json"
DIARY_LOCK = threading.Lock()
TTS_JOBS = {}
TTS_JOBS_LOCK = threading.Lock()


def load_diary():
    return json.loads(DIARY_FILE.read_text(encoding="utf-8")) if DIARY_FILE.exists() else {}


def save_diary(diary):
    DIARY_FILE.write_text(json.dumps(diary, ensure_ascii=False, indent=2), encoding="utf-8")


def append_diary_record(date: str, record: dict):
    with DIARY_LOCK:
        diary = load_diary()
        diary.setdefault(date, []).append(record)
        save_diary(dedup_diary(diary))

def dedup_diary(diary):
    """仅按记录 ID 去重；不同输入即使叙事相同也必须保留。"""
    for date, items in diary.items():
        seen = set()
        unique = []
        for item in items:
            record_id = item.get("id")
            if record_id and record_id in seen:
                continue
            if record_id:
                seen.add(record_id)
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


def generate_demo_image_narrative(image_data: bytes, input_type: str) -> str:
    """无视觉模型时，根据真实像素特征生成不同的叙事，避免固定音频。"""
    try:
        with Image.open(io.BytesIO(image_data)) as source:
            image = source.convert("RGB")
            image.thumbnail((160, 160))
            pixels = list(image.getdata())
    except Exception:
        return "这份画面被轻轻收进了今天。哪怕暂时说不清它的形状，它依然是此刻真实留下的一点回声。"

    if not pixels:
        return "空白也有自己的声音。它像一次安静的停顿，提醒你此刻仍然可以慢下来，听见自己的呼吸。"

    count = len(pixels)
    red = sum(pixel[0] for pixel in pixels) / count
    green = sum(pixel[1] for pixel in pixels) / count
    blue = sum(pixel[2] for pixel in pixels) / count
    brightness = (red + green + blue) / 3
    spread = max(red, green, blue) - min(red, green, blue)
    ink_ratio = sum(1 for pixel in pixels if min(pixel) < 235) / count

    if spread < 16:
        color_phrase = "安静的灰白"
    elif red >= green and red >= blue:
        color_phrase = "温暖的红棕"
    elif green >= red and green >= blue:
        color_phrase = "柔和的青绿"
    else:
        color_phrase = "清澈的蓝紫"

    light_phrase = "明亮轻盈" if brightness > 190 else "沉静柔和" if brightness > 105 else "深邃安静"
    variants = [
        "像一片刚刚停住的风，把没有说出口的心情留在纸面上",
        "像窗边落下的一束光，让普通的瞬间也有了被记住的理由",
        "像一次不必解释的呼吸，慢慢把此刻从忙乱中捧了出来",
        "像一封写给今天的短信，字不多，却保留着真实的温度",
        "像水面轻轻荡开的纹路，让细小的感受也拥有自己的方向",
        "像一颗刚刚发芽的种子，在安静里保存着继续生长的力量",
    ]
    variant = variants[hashlib.sha256(image_data).digest()[0] % len(variants)]

    if input_type == "doodle":
        density = "几笔留白" if ink_ratio < 0.08 else "疏落的线条" if ink_ratio < 0.28 else "饱满的笔触"
        return f"这幅涂鸦里有{density}，也有{color_phrase}的气息，整体显得{light_phrase}。它{variant}。不必画得完整，你留下的每一道痕迹，都已经在替此刻说话。"

    return f"这张照片带着{color_phrase}的气息，画面的光线{light_phrase}。它{variant}。你愿意按下快门的那个瞬间，本身就是今天值得珍藏的一小段回声。"


def process_image(image_data: bytes, input_type: str = "image") -> str:
    """处理图片：视觉理解 -> 叙事"""
    if not OPENAI_API_KEY:
        return generate_demo_image_narrative(image_data, input_type)

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
        suffix = Path(filename).suffix.lower()
        audio_mime = {
            ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
            ".ogg": "audio/ogg", ".wav": "audio/wav", ".webm": "audio/webm",
        }.get(suffix, "application/octet-stream")
        files = {"file": (filename, io.BytesIO(audio_data), audio_mime)}
        data = {"model": WHISPER_MODEL, "language": "zh"}
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
def _generate_tts_chunk(text: str) -> str | None:
    """生成不超过 5000 字的单段音频。"""
    if not DOBAO_TTS_PASSWORD:
        print("[TTS] 未配置 DOBAO_TTS_PASSWORD，跳过 TTS 生成")
        return None

    try:
        auth = base64.b64encode(f"{DOBAO_TTS_USER}:{DOBAO_TTS_PASSWORD}".encode()).decode()
        resp = requests.post(
            f"{DOBAO_TTS_URL}/api/tts",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            json={"text": text, "speaker": DOBAO_TTS_VOICE, "rate": 0, "pitch": 0},
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        audio_url = data.get("storageUrl") or data.get("url") or data.get("local_url")
        if audio_url and audio_url.startswith("/"):
            audio_url = f"{DOBAO_TTS_URL}{audio_url}"
        return audio_url
    except Exception as exc:
        print(f"[TTS 分段失败] {exc}")
        return None


def _split_tts_text(text: str, limit: int = 4500) -> list[str]:
    """按段落/句号切分长文，每段严格小于服务上限。"""
    text = text.strip()
    chunks = []
    while len(text) > limit:
        cut = max(text.rfind(mark, 0, limit) for mark in ("\n", "。", "！", "？", "；", ".", "!", "?"))
        if cut < limit // 2:
            cut = limit
        else:
            cut += 1
        chunks.append(text[:cut].strip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def generate_tts(text: str) -> str | None:
    """长文顺序分段生成；多段时合并为一个可播放 MP3。"""
    chunks = _split_tts_text(text)
    if not chunks:
        return None
    urls = []
    for index, chunk in enumerate(chunks, 1):
        print(f"[TTS] 正在生成第 {index}/{len(chunks)} 段，{len(chunk)} 字")
        url = _generate_tts_chunk(chunk)
        if not url:
            return None
        urls.append(url)
    if len(urls) == 1:
        return urls[0]

    merge_id = uuid.uuid4().hex
    parts = []
    list_file = AUDIO_DIR / f".{merge_id}.txt"
    output_file = AUDIO_DIR / f"{merge_id}.mp3"
    try:
        for index, url in enumerate(urls):
            part = AUDIO_DIR / f".{merge_id}-{index}.mp3"
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            part.write_bytes(response.content)
            parts.append(part)
        list_file.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
        subprocess.run(
            ["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_file)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120,
        )
        return f"/api/audio/{output_file.name}"
    except Exception as exc:
        print(f"[TTS 合并失败] {exc}")
        return None
    finally:
        for path in [*parts, list_file]:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


def _run_long_text_job(job_id: str, user_content: str, theme: str):
    """后台完成长文叙事、图片和完整原文音频，避免浏览器连接超时。"""
    try:
        narrative = generate_narrative(user_content)
        image_url = generate_image(narrative)
        audio_url = generate_tts(user_content)
        if not audio_url:
            raise RuntimeError("长文音频生成失败，请稍后重试")
        echo_id = uuid.uuid4().hex[:8]
        today = str(datetime.date.today())
        record = {
            "id": echo_id, "theme": theme, "user_input": user_content,
            "input_type": "text", "narrative": narrative,
            "audio_url": audio_url, "image_url": image_url,
            "audio_mode": "full_text", "created_at": datetime.datetime.now().isoformat(),
        }
        append_diary_record(today, record)
        result = {"status": "completed", "id": echo_id, "narrative": narrative,
                  "audio_url": audio_url, "image_url": image_url, "date": today}
    except Exception as exc:
        print(f"[长文任务失败] {exc}")
        result = {"status": "failed", "error": str(exc)}
    with TTS_JOBS_LOCK:
        TTS_JOBS[job_id] = result


def _image_result_url(payload: dict) -> str | None:
    """兼容 OpenAI 图片接口的 URL 与 b64_json 两种返回。"""
    items = payload.get("data") or []
    if not items:
        return None
    item = items[0]
    if item.get("url"):
        return item["url"]
    encoded = item.get("b64_json")
    if not encoded:
        return None
    try:
        image_id = f"{uuid.uuid4().hex}.png"
        (IMAGE_DIR / image_id).write_bytes(base64.b64decode(encoded, validate=True))
        return f"/api/images/{image_id}"
    except Exception as exc:
        print(f"[生图解码失败] {exc}")
        return None


def save_uploaded_photo(image_data: bytes) -> str | None:
    """保存用户原始照片的适配版本，照片流程不再调用 AI 生图。"""
    try:
        filename = f"photo-{uuid.uuid4().hex}.jpg"
        with Image.open(io.BytesIO(image_data)) as source:
            photo = source.convert("RGB")
            photo.thumbnail((1600, 1600))
            photo.save(IMAGE_DIR / filename, "JPEG", quality=88, optimize=True)
        return f"/api/images/{filename}"
    except Exception as exc:
        print(f"[原图保存失败] {exc}")
        return None


def generate_image(narrative: str, reference_image: bytes | None = None) -> str | None:
    """根据叙事生成治愈系画面；有照片/涂鸦时优先使用参考图。"""
    if not IMAGE_API_KEY:
        return None

    prompt = (
        "请根据下面的中文内容创作一张温暖、安静、细腻的治愈系插画。"
        "保留输入中的核心意象和情绪，构图简洁，有自然光与手绘质感，"
        "不要添加任何文字、水印、边框或界面元素。内容：" + narrative[:800]
    )
    headers = {"Authorization": f"Bearer {IMAGE_API_KEY}"}

    # OpenAI-compatible image edit；不支持时自动回退到文生图。
    if reference_image:
        try:
            resp = requests.post(
                f"{IMAGE_BASE_URL}/images/edits",
                headers=headers,
                data={"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024"},
                files={"image": ("reference.png", io.BytesIO(reference_image), "image/png")},
                timeout=120,
            )
            resp.raise_for_status()
            result = _image_result_url(resp.json())
            if result:
                return result
        except Exception as exc:
            print(f"[参考图生成失败，回退文生图] {exc}")

    try:
        resp = requests.post(
            f"{IMAGE_BASE_URL}/images/generations",
            headers={**headers, "Content-Type": "application/json"},
            json={"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "n": 1},
            timeout=120,
        )
        resp.raise_for_status()
        return _image_result_url(resp.json())
    except Exception as exc:
        print(f"[生图失败] {exc}")
        return None


def _run_photo_image_job(echo_id: str, narrative: str, image_data: bytes):
    """照片音频先完成；生成图随后成功时替换日历封面。"""
    generated_url = generate_image(narrative, image_data)
    with DIARY_LOCK:
        diary = load_diary()
        changed = False
        for items in diary.values():
            for item in items:
                if item.get("id") != echo_id:
                    continue
                if generated_url:
                    item["original_image_url"] = item.get("image_url")
                    item["image_url"] = generated_url
                    item["image_status"] = "generated"
                else:
                    item["image_status"] = "failed"
                changed = True
        if changed:
            save_diary(diary)

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
        "has_image_generation": bool(IMAGE_API_KEY),
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
    reference_image = None
    if input_type == "text":
        user_content = data.get("content", "").strip()
        if not user_content:
            return jsonify({"error": "内容不能为空"}), 400
        if len(user_content) > 20000:
            return jsonify({"error": "长文暂时最多支持 20000 字"}), 400
        if len(user_content) > 300:
            job_id = uuid.uuid4().hex
            with TTS_JOBS_LOCK:
                TTS_JOBS[job_id] = {"status": "processing"}
                if len(TTS_JOBS) > 100:
                    oldest = next(iter(TTS_JOBS))
                    if oldest != job_id:
                        TTS_JOBS.pop(oldest, None)
            threading.Thread(target=_run_long_text_job, args=(job_id, user_content, theme), daemon=True).start()
            return jsonify({"pending": True, "job_id": job_id}), 202
        narrative = generate_narrative(user_content)
        tts_text = user_content if len(user_content) > 300 else narrative

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
            reference_image = image_data
        except Exception:
            return jsonify({"error": "图片或涂鸦格式错误"}), 400
        narrative = process_image(image_data, input_type)
        tts_text = narrative

    # ---- 语音输入 ----
    elif input_type == "voice":
        # 语音走 form-data 传输
        return jsonify({"error": "请使用 /api/echo/voice 接口上传语音"}), 400

    else:
        return jsonify({"error": f"不支持的类型: {input_type}"}), 400

    # 根据输入内容生成专属图片与音频
    echo_id = uuid.uuid4().hex[:8]
    # 照片和涂鸦都先保留用户原图；涂鸦不再调用 Image2 重画。
    image_url = save_uploaded_photo(reference_image) if input_type in ("image", "doodle") else generate_image(narrative, reference_image)
    audio_url = generate_tts(tts_text)

    # 保存日记
    today = str(datetime.date.today())
    record = {
        "id": echo_id,
        "theme": theme,
        "user_input": data.get("content", ""),
        "input_type": input_type,
        "narrative": narrative,
        "audio_url": audio_url,
        "image_url": image_url,
        "image_status": "processing" if input_type == "image" and IMAGE_API_KEY else "original" if input_type == "doodle" and image_url else "generated" if image_url else "unavailable",
        "audio_mode": "full_text" if input_type == "text" and len(user_content) > 300 else "narrative",
        "created_at": datetime.datetime.now().isoformat(),
    }
    append_diary_record(today, record)
    if input_type == "image" and IMAGE_API_KEY:
        threading.Thread(target=_run_photo_image_job, args=(echo_id, narrative, reference_image), daemon=True).start()

    return jsonify({
        "id": echo_id,
        "narrative": narrative,
        "audio_url": audio_url,
        "image_url": image_url,
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

    # Step 3: 根据识别后的内容生成图片，并生成 TTS 音频
    echo_id = uuid.uuid4().hex[:8]
    image_url = generate_image(narrative)
    try:
        audio_url = generate_tts(narrative)
    except Exception as e:
        print(f"[TTS 异常] {e}")
        audio_url = None

    # 保存
    today = str(datetime.date.today())
    append_diary_record(today, {
        "id": echo_id,
        "theme": theme,
        "user_input": transcribed,
        "input_type": "voice",
        "narrative": narrative,
        "audio_url": audio_url,
        "image_url": image_url,
        "created_at": datetime.datetime.now().isoformat(),
    })

    return jsonify({
        "id": echo_id,
        "transcribed": transcribed,
        "narrative": narrative,
        "audio_url": audio_url,
        "image_url": image_url,
        "date": today,
    })


@app.route("/api/echo/jobs/<job_id>")
def api_echo_job(job_id):
    with TTS_JOBS_LOCK:
        job = TTS_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "任务不存在或已过期"}), 404
    return jsonify(job)


@app.route("/api/audio/<filename>")
def api_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)


@app.route("/api/images/<filename>")
def api_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


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
