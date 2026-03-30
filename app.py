from flask import Flask, render_template, request, send_file, jsonify
from playwright.sync_api import sync_playwright
import requests
import io
import zipfile
import re
from urllib.parse import urljoin, urlparse, unquote
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
            
            # Extract image URLs checking dataset as well for lazy loads and context info
            images_data = page.evaluate("""
            () => {
                let imagesData = new Map();
                document.querySelectorAll('img').forEach(img => {
                    let url = img.dataset.src || img.src;
                    if (!url) return;
                    if (url.startsWith('data:')) return;
                    
                    let infoLines = [];
                    
                    if (img.alt && img.alt.length > 3 && !img.alt.includes('http')) infoLines.push(img.alt.trim());
                    else if (img.title && img.title.length > 3) infoLines.push(img.title.trim());

                    let figure = img.closest('figure');
                    if (figure) {
                        let caption = figure.querySelector('figcaption');
                        if (caption && caption.innerText.trim()) {
                            infoLines.push(caption.innerText.trim());
                        }
                    }

                    // Special handling for fandom wikis (portable infoboxes)
                    let infobox = img.closest('aside.portable-infobox, .portable-infobox');
                    if (infobox) {
                        let titleEl = infobox.querySelector('.pi-title');
                        if (titleEl && titleEl.innerText.trim()) infoLines.push(titleEl.innerText.trim());
                        
                        Array.from(infobox.querySelectorAll('.pi-data')).forEach(el => {
                            let label = el.querySelector('.pi-data-label');
                            let val = el.querySelector('.pi-data-value');
                            if (label && val) infoLines.push(label.innerText.trim() + ": " + val.innerText.trim());
                            else if (val) infoLines.push(val.innerText.trim());
                        });
                    }

                    infoLines = [...new Set(infoLines)];
                    let finalInfo = infoLines.join('\\n').trim();

                    if (!imagesData.has(url) || finalInfo.length > (imagesData.get(url) || "").length) {
                        imagesData.set(url, finalInfo);
                    }
                });
                return Array.from(imagesData.entries()).map(([url, info]) => ({url, info}));
            }
            """)
            
            browser.close()
            
            # Filter valid URLs
            valid_images = []
            seen_urls = set()
            for item in images_data:
                img = item.get('url')
                info = item.get('info', '')
                if not img: continue
                if img.startswith('data:'): continue
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
                if 'static.wikia.nocookie.net' in abs_url and '?' in abs_url:
                    abs_url = abs_url.split('?')[0]
                
                if abs_url not in seen_urls:
                    seen_urls.add(abs_url)
                    valid_images.append({'url': abs_url, 'info': info})
                    
            return jsonify({'images': valid_images})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def download_image(item):
    if isinstance(item, str):
        url = item
        info = ""
    else:
        url = item.get('url')
        info = item.get('info', "")
        
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, timeout=10, stream=True, headers=headers)
        if response.status_code == 200:
            parsed = urlparse(url)
            orig_filename = unquote(parsed.path.split('/')[-1])
            orig_filename = orig_filename.split('?')[0]
            
            parts = orig_filename.rsplit('.', 1)
            ext = parts[1] if len(parts) == 2 else ''
            
            if not orig_filename or not ext:
                content_type = response.headers.get('Content-Type', '')
                ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
                if ext == 'jpeg': ext = 'jpg'
                if ext == 'svg+xml': ext = 'svg'

            filename = ""
            
            if info:
                s = re.sub(r'[^\w\s\-\(\)\[\]#]', '', info).strip()
                s = re.sub(r'[-\s]+', '_', s)
                clean_info = s[:120].strip('_')
                if clean_info:
                    filename = f"{clean_info}.{ext}"
                    
            if not filename:
                s = re.sub(r'[^\w\s\-\(\)\[\]#]', '', orig_filename.rsplit('.', 1)[0]).strip()
                s = re.sub(r'[-\s]+', '_', s)
                clean_orig = s.strip('_')
                if not clean_orig:
                    clean_orig = f"image_{hash(url)}"
                filename = f"{clean_orig}.{ext}"
                    
            return {"filename": filename, "data": response.content}
    except Exception as e:
        print(f"Failed to download {url}: {e}")
    return None

@app.route('/api/download', methods=['POST'])
def download():
    data = request.json
    items = data.get('items', [])
    
    if not items:
        # Fallback to old behavior if frontend hasn't updated
        urls = data.get('urls', [])
        items = [{'url': url, 'info': ''} for url in urls]
        
    if not items:
        return jsonify({'error': 'No URLs provided'}), 400
        
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(download_image, items)
            
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
