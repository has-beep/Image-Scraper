from flask import Flask, render_template, request, send_file, jsonify
from playwright.sync_api import sync_playwright
import requests
import io
import zipfile
import re
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    target_url = data.get('url')
    if not target_url:
        return jsonify({'error': 'URL is required'}), 400
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Use a real user agent to bypass basic anti-bot screens
            page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Navigate and wait for DOM instead of networkidle to prevent ad-tracker timeouts
            try:
                page.goto(target_url, wait_until='domcontentloaded', timeout=20000)
            except Exception as e:
                print(f"Warning: navigation timeout: {e}")
            
            # Scroll down to trigger lazy loading images common on wikis
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
            except:
                pass
            
            # Extract image URLs checking dataset as well for lazy loads
            images = page.evaluate("""
            () => {
                let urls = new Set();
                document.querySelectorAll('img').forEach(img => {
                    if (img.dataset.src) urls.add(img.dataset.src);
                    else if (img.src) urls.add(img.src);
                });
                return Array.from(urls);
            }
            """)
            
            browser.close()
            
            # Filter valid URLs
            valid_images = []
            for img in images:
                if not img: continue
                if img.startswith('data:'):
                    continue
                # Ensure absolute URL
                abs_url = urljoin(target_url, img)
                
                # --- High Resolution Extraction Hacks ---
                # 1. Fandom / Wikia: Remove downscaling params to get the raw upload
                if '/revision/latest' in abs_url:
                    abs_url = abs_url.split('/revision/latest')[0]
                
                # 2. Pinterest: Switch thumbnail path to originals path
                if 'i.pinimg.com' in abs_url:
                    abs_url = re.sub(r'/(\d+x|736x|564x|474x)/', '/originals/', abs_url)
                    
                # 3. Strip general query strings that might restrict size (unless it's a dynamic renderer)
                # (We hold off on stripping all queries since some sites need them, but Fandom definitely doesn't for base files)
                if 'static.wikia.nocookie.net' in abs_url and '?' in abs_url:
                    abs_url = abs_url.split('?')[0]
                
                if abs_url not in valid_images:
                    valid_images.append(abs_url)
                    
            return jsonify({'images': valid_images})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def download_image(url):
    try:
        # Provide a User-Agent to avoid simple blocks
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, timeout=10, stream=True, headers=headers)
        if response.status_code == 200:
            # Try to guess filename from URL
            parsed = urlparse(url)
            filename = parsed.path.split('/')[-1]
            # Strip query params from filename if any
            filename = filename.split('?')[0]
            
            if not filename or '.' not in filename:
                content_type = response.headers.get('Content-Type', '')
                ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
                if ext == 'jpeg': ext = 'jpg'
                if ext == 'svg+xml': ext = 'svg'
                filename = f"image_{hash(url)}.{ext}"
                
            # Read image content
            return {"filename": filename, "data": response.content}
    except Exception as e:
        print(f"Failed to download {url}: {e}")
    return None

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    urls = data.get('urls', [])
    
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400
        
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Download concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(download_image, urls)
            
            count = 1
            for result in results:
                if result:
                    name = result['filename']
                    parts = name.rsplit('.', 1)
                    if len(parts) == 2:
                        unique_name = f"{parts[0]}_{count}.{parts[1]}"
                    else:
                        unique_name = f"{name}_{count}"
                    
                    zf.writestr(unique_name, result['data'])
                    count += 1
                
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='gravitas_raw_images.zip'
    )

if __name__ == '__main__':
    app.run(debug=True, port=3000)
