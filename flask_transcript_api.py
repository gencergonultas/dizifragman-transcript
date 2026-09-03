#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Transcript Flask API
Render.com ve Docker için optimize edilmiş 7/24 kesintisiz çalışan API servisi.
"""

import os
import sys
import re
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

TRANSCRIPT_API_AVAILABLE = False
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_API_AVAILABLE = True
except Exception as e:
    print(f"⚠️ youtube-transcript-api import hatası: {e}")


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
    elif isinstance(fetched, list):
        raw_data = fetched
    else:
        raw_data = list(fetched)

    transcript = []
    for item in raw_data:
        text = normalize_text(str(item.get("text", "")))
        if not text:
            continue
        transcript.append(
            {
                "start": float(item.get("start", 0) or 0),
                "duration": float(item.get("duration", 0) or 0),
                "text": text,
            }
        )

    full_text = " ".join([entry["text"] for entry in transcript]).strip()
    lang = getattr(fetched, "language_code", "") if not isinstance(fetched, list) else "auto"

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
    # 1. v1.x instance API'yi dene
    try:
        api = YouTubeTranscriptApi()
        # Direct fetch: once tr, sonra tr+en
        for m_name, langs in [("tr", ["tr", "tr-TR"]), ("tr-en", ["tr", "tr-TR", "en", "en-US"])]:
            try:
                res = api.fetch(video_id, languages=langs)
                return format_transcript_result(res, video_id, f"v1-fetch-{m_name}")
            except Exception:
                pass

        # api.list() dene
        try:
            t_list = api.list(video_id)
            for m_name, fn in [
                ("find-tr", lambda: t_list.find_transcript(["tr", "tr-TR"]).fetch()),
                ("gen-tr", lambda: t_list.find_generated_transcript(["tr", "tr-TR"]).fetch()),
                ("find-en", lambda: t_list.find_transcript(["en", "en-US"]).fetch()),
            ]:
                try:
                    res = fn()
                    return format_transcript_result(res, video_id, f"v1-list-{m_name}")
                except Exception:
                    pass

            # Son care ilk eleman
            first = next(iter(t_list))
            return format_transcript_result(first.fetch(), video_id, "v1-first")
        except Exception:
            pass
    except Exception:
        pass

    # 2. v0.6.x static API fallback
    try:
        if hasattr(YouTubeTranscriptApi, 'get_transcript'):
            for langs in [["tr", "tr-TR"], ["tr", "tr-TR", "en", "en-US"], None]:
                try:
                    kwargs = {"languages": langs} if langs else {}
                    raw = YouTubeTranscriptApi.get_transcript(video_id, **kwargs)
                    if raw:
                        return format_transcript_result(raw, video_id, "v0-get_transcript")
                except Exception:
                    pass
    except Exception:
        pass

    return {
        "success": False,
        "error": "Bu video için altyazı veya transkript bulunamadı.",
        "video_id": video_id,
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
        # Ana sayfa bilgisi
        if request.path == '/':
            return jsonify({
                "service": "DiziFragman YouTube Transcript API",
                "status": "online",
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
    return jsonify({
        "status": "healthy",
        "service": "YouTube Transcript API",
        "transcript_api_available": TRANSCRIPT_API_AVAILABLE,
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🎬 DiziFragman Transcript API {port} portunda başlatılıyor...")
    app.run(host='0.0.0.0', port=port)
