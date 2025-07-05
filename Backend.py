from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp
import os
import uuid
import base64
import requests
from threading import Thread
from time import sleep

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "temp_downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.route('/')
def index():
    return jsonify({"message": "Welcome to the Instagram Reel Downloader API!"})
   
@app.route('/get-reel-thumbnail', methods=['POST'])
def get_thumbnail():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' in request"}), 400

    try:
        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'force_generic_extractor': False
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                thumbnail_url = info.get("thumbnail", "")
                video_id = info.get("id", "unknown")
        except yt_dlp.utils.DownloadError as de:
            return jsonify({"error": f"yt_dlp error: {str(de)}"}), 400
        except Exception as e:
            return jsonify({"error": f"yt_dlp general error: {str(e)}"}), 400

        if not thumbnail_url:
            return jsonify({"error": "No thumbnail found for the provided URL."}), 404

        try:
            response = requests.get(thumbnail_url)
            response.raise_for_status()
        except requests.RequestException as re:
            return jsonify({"error": f"Failed to fetch thumbnail image: {str(re)}"}), 502

        image_data = base64.b64encode(response.content).decode('utf-8')
        mime = response.headers.get("Content-Type", "image/jpeg")

        return jsonify({
            "shortcode": video_id,
            "thumbnail_url": thumbnail_url,
            "thumbnail_base64": f"data:{mime};base64,{image_data}"
        })

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/download-reel', methods=['POST'])
def download_reel():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' in request"}), 400

    uid = str(uuid.uuid4())
    filename_template = os.path.join(DOWNLOAD_DIR, f"{uid}.%(ext)s")
    ydl_opts = {
        'outtmpl': filename_template,
        'format': 'mp4/best',
        'quiet': True,
    }

    try:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as de:
            return jsonify({"error": f"yt_dlp error: {str(de)}"}), 400
        except Exception as e:
            return jsonify({"error": f"yt_dlp general error: {str(e)}"}), 400

        if not os.path.exists(downloaded_file):
            return jsonify({"error": f"Download failed: File '{downloaded_file}' not found after download."}), 500

        @after_this_request
        def schedule_delete(response):
            def delete_later(path):
                sleep(1800)  # 30 minutes
                try:
                    os.remove(path)
                    print(f"[INFO] Deleted {path}")
                except Exception as e:
                    print(f"[Cleanup error] {e}")
            Thread(target=delete_later, args=(downloaded_file,), daemon=True).start()
            return response

        try:
            return send_file(
                downloaded_file,
                as_attachment=True,
                download_name=os.path.basename(downloaded_file),
                mimetype="video/mp4"
            )
        except Exception as e:
            return jsonify({"error": f"Flask send_file error: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, threaded=True)