from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    try:
        page.goto("https://hunterxhunter.fandom.com/wiki/Greed_Island_Card_Lists", wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        print(f"Goto Exception: {e}")
    
    # Auto-scroll to bottom to trigger lazy loading
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(2000) # wait 2 seconds for lazy images
    
    # Extract images checking data-src, src, and srcset
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
    print(f"Found {len(images)} images.")
    # Show first 5
    for img in images[:5]:
        print(img)
    browser.close()
