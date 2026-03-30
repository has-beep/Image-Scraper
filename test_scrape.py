from playwright.sync_api import sync_playwright
import time
import json

with sync_playwright() as p:
    # Use anti-detect arguments
    browser = p.chromium.launch(
        headless=False,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-web-security',
            '--window-size=1920,1080'
        ]
    )
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080}
    )
    
    # Add an init script to bypass webdriver detection
    context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    """)
    
    page = context.new_page()
    try:
        page.goto("https://www.britishmuseum.org/collection/galleries", wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        print(f"Goto Exception: {e}")
    
    # Attempt to dismiss cookie banner
    try:
        # British museum specific or general cookie buttons
        page.evaluate("""
        () => {
            const buttons = Array.from(document.querySelectorAll('button, a'));
            const acceptBtn = buttons.find(b => 
                b.textContent && (
                    b.textContent.toLowerCase().includes('allow all cookies') ||
                    b.textContent.toLowerCase().includes('accept all cookies') ||
                    b.textContent.toLowerCase().includes('accept')
                )
            );
            if (acceptBtn) acceptBtn.click();
        }
        """)
        page.wait_for_timeout(2000)
    except Exception as e:
        print("Cookie handling error:", e)

    # Scroll progressively to load lazy elements
    page.evaluate("""
    async () => {
        await new Promise((resolve) => {
            let totalHeight = 0;
            let distance = 500;
            let timer = setInterval(() => {
                let scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;

                if(totalHeight >= scrollHeight - window.innerHeight){
                    clearInterval(timer);
                    resolve();
                }
            }, 200);
        });
    }
    """)
    
    page.wait_for_timeout(2000)
    
    # Enhanced extraction
    images_data = page.evaluate("""
    () => {
        let urls = new Set();
        
        // 1. Standard img tags
        document.querySelectorAll('img').forEach(img => {
            if (img.dataset.src) urls.add(img.dataset.src);
            else if (img.src) urls.add(img.src);
            
            if (img.dataset.lazySrc) urls.add(img.dataset.lazySrc);
            if (img.srcset) {
                // Split srcset and get first URL of each
                img.srcset.split(',').forEach(item => {
                    let parts = item.trim().split(' ');
                    if (parts.length > 0) urls.add(parts[0]);
                });
            }
        });
        
        // 2. Picture source tags
        document.querySelectorAll('source').forEach(source => {
            if (source.srcset) {
                source.srcset.split(',').forEach(item => {
                    let parts = item.trim().split(' ');
                    if (parts.length > 0) urls.add(parts[0]);
                });
            }
        });
        
        // 3. Background images
        document.querySelectorAll('*').forEach(el => {
            let bg = window.getComputedStyle(el).backgroundImage;
            if (bg && bg !== 'none' && bg.includes('url(')) {
                let match = bg.match(/url\(["']?([^"')]+)["']?\)/);
                if (match && !match[1].startsWith('data:')) {
                    urls.add(match[1]);
                }
            }
        });
        
        return Array.from(urls);
    }
    """)
    
    print(f"Total extracted potential image URLs: {len(images_data)}")
    for u in images_data[:10]:
        print(u)
        
    browser.close()
