#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Transcript Flask API
Render.com ve Docker için optimize edilmiş 7/24 kesintisiz çalışan API servisi.
Webshare rotating residential proxy desteği ile YouTube IP engellerini aşar.
"""

import os
import sys
import re
import urllib.parse
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TRANSCRIPT_API_AVAILABLE = False
PROXY_SUPPORT_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
    TRANSCRIPT_API_AVAILABLE = True
    PROXY_SUPPORT_AVAILABLE = True
except Exception as e:
    print(f"⚠️ youtube-transcript-api import hatası: {e}")

# Varsayılan Webshare rotating residential proxy
DEFAULT_PROXY_URL = "http://hzpvxqft-rotate:thylo9jqyzrq@p.webshare.io:80"


def build_transcript_api():
    """Proxy destekli YouTubeTranscriptApi nesnesi oluşturur."""
    proxy_url = os.environ.get("TRANSCRIPT_PROXY_URL", "").strip() or DEFAULT_PROXY_URL
    if not proxy_url:
        return YouTubeTranscriptApi()

    if not PROXY_SUPPORT_AVAILABLE:
        print("⚠️ youtube-transcript-api proxy desteği bulunamadı, doğrudan bağlanılıyor.")
        return YouTubeTranscriptApi()

    try:
        parsed = urllib.parse.urlparse(proxy_url)
        hostname = (parsed.hostname or "").lower()
        if "webshare" in hostname:
            # Webshare rotating residential proxy: bağlantıyı her istekte kapatarak IP rotasyonunu tetikler
            # ve engellenirse 10 defaya kadar yeni IP dener.
            proxy_config = WebshareProxyConfig(
                proxy_username=parsed.username or "hzpvxqft-rotate",
                proxy_password=parsed.password or "thylo9jqyzrq",
                domain_name=hostname or "p.webshare.io",
                proxy_port=parsed.port or 80,
                retries_when_blocked=10,
            )
        else:
            proxy_config = GenericProxyConfig(
                http_url=proxy_url,
                https_url=proxy_url,
            )
        return YouTubeTranscriptApi(proxy_config=proxy_config)
    except Exception as e:
        print(f"⚠️ Proxy yapılandırma hatası: {e}, varsayılan API oluşturuluyor.")
        return YouTubeTranscriptApi()


def extract_video_id(url_or_id):
    if not url_or_id:
        return None
    url_or_id = str(url_or_id).strip()
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id

    patterns = [
        r'(?:v=|\/)([a-zA-Z0-9_-]{11})(?:[&?].*)?$',
        r'(?:embed\/|v\/|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None


def normalize_text(text: str) -> str:
    text = (text or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_transcript_result(fetched, video_id: str, method: str) -> dict:
    if hasattr(fetched, 'to_raw_data'):
        raw_data = fetched.to_raw_data()
    else:
        raw_data = fetched

    transcript = []
    for item in raw_data:
        if hasattr(item, 'text'):
            t_text = item.text
            t_start = item.start
            t_dur = item.duration
        elif isinstance(item, dict):
            t_text = item.get("text", "")
            t_start = item.get("start", 0)
            t_dur = item.get("duration", 0)
        else:
            continue

        text = normalize_text(str(t_text or ""))
        if not text:
            continue
        transcript.append(
            {
                "start": float(t_start or 0),
                "duration": float(t_dur or 0),
                "text": text,
            }
        )

    full_text = " ".join([entry["text"] for entry in transcript]).strip()
    lang = getattr(fetched, "language_code", "auto")

    return {
        "success": True,
        "video_id": video_id,
        "full_text": full_text,
        "text": full_text,
        "transcript": transcript,
        "count": len(transcript),
        "language": lang,
        "lang": lang,
        "word_count": len(full_text.split()),
        "char_count": len(full_text),
        "method": method,
    }


def fetch_transcript_core(video_id: str) -> dict:
    errors = []

    # 1. v1.x instance API (Proxy destekli)
    try:
        api = build_transcript_api()

        # Doğrudan fetch denemeleri: önce Türkçe, sonra Türkçe+İngilizce
        for m_name, langs in [
            ("tr", ["tr", "tr-TR"]),
            ("tr-en", ["tr", "tr-TR", "en", "en-US"]),
        ]:
            try:
                res = api.fetch(video_id, languages=langs)
                return format_transcript_result(res, video_id, f"v1-fetch-{m_name}")
            except Exception as e:
                errors.append(f"v1-fetch-{m_name}: {type(e).__name__}: {str(e)}")

        # api.list() ile mevcut tüm dilleri tara
        try:
            t_list = api.list(video_id)

            # Önce Türkçe manuel ve otomatik (ASR) altyazılar
            for m_name, fn in [
                ("find-tr", lambda: t_list.find_transcript(["tr", "tr-TR"]).fetch()),
                ("gen-tr", lambda: t_list.find_generated_transcript(["tr", "tr-TR"]).fetch()),
                ("find-en", lambda: t_list.find_transcript(["en", "en-US"]).fetch()),
                ("gen-en", lambda: t_list.find_generated_transcript(["en", "en-US"]).fetch()),
            ]:
                try:
                    res = fn()
                    return format_transcript_result(res, video_id, f"v1-list-{m_name}")
                except Exception as e:
                    errors.append(f"v1-list-{m_name}: {type(e).__name__}: {str(e)}")

            # Herhangi bir dildeki ilk altyazı
            for t in t_list:
                try:
                    return format_transcript_result(t.fetch(), video_id, f"v1-any-{t.language_code}")
                except Exception as e:
                    errors.append(f"v1-any-{t.language_code}: {type(e).__name__}: {str(e)}")
        except Exception as e:
            errors.append(f"v1-list: {type(e).__name__}: {str(e)}")
    except Exception as e:
        errors.append(f"v1-init: {type(e).__name__}: {str(e)}")

    # 2. v0.6.x static fallback (eski sürüm uyumluluğu)
    try:
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            for langs in [["tr", "tr-TR"], ["tr", "tr-TR", "en", "en-US"], None]:
                try:
                    kwargs = {"languages": langs} if langs else {}
                    raw = YouTubeTranscriptApi.get_transcript(video_id, **kwargs)
                    if raw:
                        return format_transcript_result(raw, video_id, "v0-get_transcript")
                except Exception as e:
                    errors.append(f"v0-get: {type(e).__name__}: {str(e)}")
    except Exception as e:
        errors.append(f"v0-init: {type(e).__name__}: {str(e)}")

    return {
        "success": False,
        "error": "Bu video için altyazı veya transkript bulunamadı.",
        "video_id": video_id,
        "details": errors,
    }


@app.route('/api/get-transcript', methods=['GET', 'POST'])
@app.route('/transcript', methods=['GET', 'POST'])
@app.route('/', methods=['GET'])
def get_transcript():
    video_param = request.args.get('v') or request.args.get('video_id') or request.args.get('url')
    if request.method == 'POST' and not video_param:
        data = request.get_json(silent=True) or {}
        video_param = data.get('video_id') or data.get('v') or data.get('video_url') or data.get('url')

    if not video_param:
        if request.path == '/':
            proxy_url = os.environ.get("TRANSCRIPT_PROXY_URL", "").strip() or DEFAULT_PROXY_URL
            return jsonify({
                "service": "DiziFragman YouTube Transcript API",
                "status": "online",
                "proxy_active": bool(proxy_url),
                "usage": "/api/get-transcript?v=VIDEO_ID",
                "health": "/health"
            })
        return jsonify({"success": False, "error": "video_id veya v parametresi gerekli"}), 400

    video_id = extract_video_id(video_param)
    if not video_id:
        return jsonify({"success": False, "error": "Geçersiz video ID"}), 400

    result = fetch_transcript_core(video_id)
    status_code = 200 if result.get("success") else 404
    return jsonify(result), status_code


@app.route('/health', methods=['GET'])
def health():
    proxy_url = os.environ.get("TRANSCRIPT_PROXY_URL", "").strip() or DEFAULT_PROXY_URL
    return jsonify({
        "status": "healthy",
        "service": "YouTube Transcript API",
        "transcript_api_available": TRANSCRIPT_API_AVAILABLE,
        "proxy_enabled": bool(proxy_url),
        "proxy_type": "webshare" if "webshare" in proxy_url else ("generic" if proxy_url else "none"),
        "proxy_support_available": PROXY_SUPPORT_AVAILABLE,
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎬 DiziFragman Transcript API {port} portunda başlatılıyor...")
    app.run(host='0.0.0.0', port=port)
