#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Transcript Flask API
Fragman-duzenle.php ile entegre çalışır

Kurulum:
    pip install flask flask-cors youtube-transcript-api

Çalıştırma:
    python flask_transcript_api.py
    
Test:
    curl "http://localhost:5000/api/get-transcript?v=VIDEO_ID"
"""

import os
import sys
import re
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Tüm origin'lere izin ver (CORS)

# youtube-transcript-api yüklü mü kontrol et
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        CouldNotRetrieveTranscript,
    )
    TRANSCRIPT_API_AVAILABLE = True
except Exception as e:
    TRANSCRIPT_API_AVAILABLE = False
    print(f"⚠️  youtube-transcript-api import hatası: {e}")


def extract_video_id(url_or_id):
    """YouTube URL'den veya direkt ID'den video ID çıkar"""
    if not url_or_id:
        return None
    
    # Zaten sadece ID ise (11 karakter)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None


@app.route('/api/get-transcript', methods=['GET', 'POST'])
def get_transcript():
    """
    YouTube video transcript'ini alır
    
    GET parametreleri:
        v: Video ID
        url: YouTube URL
    
    POST body (JSON):
        video_id: Video ID
        video_url: YouTube URL
    """
    
    if not TRANSCRIPT_API_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'youtube-transcript-api yüklü değil. pip install youtube-transcript-api'
        }), 500
    
    try:
        # GET veya POST'dan parametreleri al
        if request.method == 'GET':
            video_id = request.args.get('v') or extract_video_id(request.args.get('url', ''))
        else:
            data = request.get_json() or {}
            video_id = data.get('video_id') or extract_video_id(data.get('video_url', ''))
        
        if not video_id:
            return jsonify({
                'success': False,
                'error': 'video_id veya video_url gerekli'
            }), 400
        
        transcript = None
        language = None
        
        # Mevcut transkriptleri listele
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # 1. Türkçe manuel altyazı var mı?
            try:
                tr_transcript = transcript_list.find_transcript(['tr'])
                transcript = tr_transcript.fetch()
                language = 'tr'
            except NoTranscriptFound:
                pass
            
            # 2. Türkçe yoksa, otomatik oluşturulan Türkçe var mı?
            if not transcript:
                try:
                    for t in transcript_list:
                        if t.is_generated and t.language_code in ['tr', 'tr-TR']:
                            transcript = t.fetch()
                            language = 'tr-auto'
                            break
                except Exception:
                    pass
            
            # 3. Hala yoksa, herhangi bir dili Türkçeye çevir
            if not transcript:
                try:
                    generated = transcript_list.find_generated_transcript(['en', 'tr'])
                    transcript = generated.translate('tr').fetch()
                    language = 'tr-translated'
                except Exception:
                    try:
                        manual = transcript_list.find_manually_created_transcript(['en', 'tr'])
                        transcript = manual.fetch()
                        language = manual.language_code
                    except Exception:
                        pass
            
            # 4. Son çare: ne varsa al
            if not transcript:
                for t in transcript_list:
                    transcript = t.fetch()
                    language = t.language_code
                    break
                    
        except TranscriptsDisabled:
            return jsonify({
                'success': False,
                'error': 'Bu videoda altyazılar devre dışı',
                'video_id': video_id
            }), 404
            
        except (NoTranscriptFound, CouldNotRetrieveTranscript):
            return jsonify({
                'success': False,
                'error': 'Bu video için hiç altyazı yok',
                'video_id': video_id
            }), 404
        
        if not transcript:
            return jsonify({
                'success': False,
                'error': 'Altyazı bulunamadı',
                'video_id': video_id
            }), 404
        
        # Metni birleştir
        full_text = ' '.join([
            entry['text'].replace('\n', ' ') 
            for entry in transcript
        ])
        
        # Temizle (gereksiz boşlukları kaldır)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'language': language,
            'full_text': full_text,
            'word_count': len(full_text.split()),
            'char_count': len(full_text)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__,
            'trace': traceback.format_exc()
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """API sağlık kontrolü"""
    return jsonify({
        'status': 'healthy',
        'service': 'YouTube Transcript API',
        'transcript_api_available': TRANSCRIPT_API_AVAILABLE
    })


@app.route('/transcript/<video_id>', methods=['GET'])
def get_transcript_simple(video_id):
    """Basit endpoint: /transcript/VIDEO_ID"""
    # GET parametresi olarak ayarla
    from werkzeug.datastructures import ImmutableMultiDict
    request.args = ImmutableMultiDict([('v', video_id)])
    return get_transcript()


@app.route('/', methods=['GET'])
def index():
    """Ana sayfa - API dokümantasyonu"""
    return '''
    <html>
    <head>
        <title>YouTube Transcript API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
            pre { background: #f4f4f4; padding: 15px; border-radius: 8px; overflow-x: auto; }
            h1 { color: #cc0000; }
            .endpoint { background: #e8f5e9; padding: 10px; border-radius: 8px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <h1>🎬 YouTube Transcript API</h1>
        <p>YouTube videolarından altyazı/transkript çekmek için basit API.</p>
        
        <h2>Endpoint'ler</h2>
        
        <div class="endpoint">
            <strong>GET</strong> <code>/api/get-transcript?v=VIDEO_ID</code>
            <p>Video ID ile transkript al</p>
        </div>
        
        <div class="endpoint">
            <strong>GET</strong> <code>/transcript/VIDEO_ID</code>
            <p>Kısa URL ile transkript al</p>
        </div>
        
        <div class="endpoint">
            <strong>GET</strong> <code>/health</code>
            <p>API sağlık kontrolü</p>
        </div>
        
        <h2>Örnek İstek</h2>
        <pre>curl "http://localhost:5000/api/get-transcript?v=dQw4w9WgXcQ"</pre>
        
        <h2>Örnek Yanıt</h2>
        <pre>{
  "success": true,
  "video_id": "dQw4w9WgXcQ",
  "language": "tr",
  "full_text": "Merhaba dünya...",
  "word_count": 150,
  "char_count": 850
}</pre>

        <p><a href="/health">API Durumu</a></p>
    </body>
    </html>
    '''


if __name__ == '__main__':
    print("=" * 50)
    print("🎬 YouTube Transcript API Başlatılıyor...")
    print("=" * 50)
    print(f"📦 youtube-transcript-api: {'✅ Yüklü' if TRANSCRIPT_API_AVAILABLE else '❌ Yüklü değil'}")
    print()
    print("🌐 Adres: http://localhost:5000")
    print("📖 Dokümantasyon: http://localhost:5000/")
    print("❤️  Sağlık: http://localhost:5000/health")
    print()
    print("Örnek kullanım:")
    print('  curl "http://localhost:5000/api/get-transcript?v=VIDEO_ID"')
    print("=" * 50)
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
