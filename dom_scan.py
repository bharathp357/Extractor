"""Quick DOM diagnostic for Gemini and ChatGPT."""
import time
from providers.browser_manager import get_browser_manager

bm = get_browser_manager()
driver = bm.driver

for provider in ["gemini"]:
    print(f"\n{'='*60}")
    print(f"  SCANNING: {provider}")
    print(f"{'='*60}")

    if not bm.has_tab(provider):
        print(f"  [!] No tab for {provider}")
        continue

    bm.switch_to(provider)
    time.sleep(1)

    print(f"  URL: {driver.current_url}")

    # Test selectors
    selectors = [
        'message-content.model-response-text .markdown',
        'model-response .markdown',
        'message-content .markdown',
        '.markdown-main-panel',
        'div.response-container-content',
        'div.model-response-text',
        'message-content.model-response-text',
        'model-response',
        'message-content',
        '.response-container .markdown',
        'div[class*="response"]',
        'div[class*="markdown"]',
        '.conversation-container',
        'turn-content',
        'model-response-text',
    ]

    print("\n  --- Selector Results ---")
    for sel in selectors:
        try:
            els = driver.find_elements("css selector", sel)
            if els:
                last_text = (els[-1].text or "")[:120].replace("\n", " | ")
                print(f"  [{len(els):2d}] {sel}")
                print(f"       -> {last_text}")
        except Exception as e:
            print(f"  [ERR] {sel}: {e}")

    # Broader scan via JS
    print("\n  --- Broader DOM Scan (elements with 100+ chars) ---")
    js = """
    var all = document.querySelectorAll('*');
    var results = [];
    for (var i = 0; i < all.length; i++) {
        var el = all[i];
        var t = (el.innerText || '').trim();
        if (t.length > 100 && t.length < 1500) {
            var tag = el.tagName.toLowerCase();
            var cls = el.className ? el.className.toString().substring(0, 80) : '';
            results.push({
                tag: tag,
                cls: cls,
                len: t.length,
                preview: t.substring(0, 120).replace(/\\n/g, ' | ')
            });
        }
    }
    return results.slice(-25);
    """
    try:
        results = driver.execute_script(js)
        for r in results:
            print(f"  <{r['tag']}> class='{r['cls']}' len={r['len']}")
            print(f"       -> {r['preview']}")
    except Exception as e:
        print(f"  [ERR] JS scan: {e}")

print("\nDone.")
