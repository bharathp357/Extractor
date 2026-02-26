"""
Diagnostic script: navigate to Google AI Mode, dump full page source and text.
This helps us find the REAL CSS selectors / DOM structure.
"""
import time
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions

def run_diagnostic():
    opts = ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    driver = webdriver.Chrome(options=opts)
    driver.implicitly_wait(2)
    
    query = "What is Python programming language"
    encoded_q = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_q}&udm=50"
    
    print(f"[1] Navigating to: {url}")
    driver.get(url)
    
    print("[2] Waiting 15 seconds for AI response to generate...")
    time.sleep(15)
    
    # Dump page source (HTML)
    print("[3] Saving page source...")
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("    -> debug_page.html saved")
    
    # Dump visible text
    print("[4] Saving visible text...")
    body = driver.find_element(By.TAG_NAME, "body")
    body_text = body.text
    with open("debug_text.txt", "w", encoding="utf-8") as f:
        f.write(body_text)
    print(f"    -> debug_text.txt saved ({len(body_text)} chars)")
    
    # Try to find interesting elements with JS
    print("[5] Analyzing DOM structure...")
    js_analysis = """
    var results = [];
    
    // Find all elements with data attributes containing 'ai'
    var allEls = document.querySelectorAll('*');
    var aiAttrs = {};
    var classNames = {};
    
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        var text = (el.innerText || '').trim();
        
        // Skip elements with very short or very long text
        if (text.length < 100 || text.length > 20000) continue;
        
        // Record class names of substantial elements
        if (el.className && typeof el.className === 'string') {
            var classes = el.className.split(' ').filter(c => c.length > 0);
            for (var j = 0; j < classes.length; j++) {
                if (!classNames[classes[j]]) {
                    classNames[classes[j]] = { count: 0, textLen: 0, tag: el.tagName };
                }
                classNames[classes[j]].count++;
                classNames[classes[j]].textLen = Math.max(classNames[classes[j]].textLen, text.length);
            }
        }
        
        // Record data attributes
        for (var k = 0; k < el.attributes.length; k++) {
            var attr = el.attributes[k];
            if (attr.name.startsWith('data-') || attr.name === 'jsname' || attr.name === 'jscontroller') {
                var key = attr.name + '=' + attr.value;
                if (!aiAttrs[key]) {
                    aiAttrs[key] = { textLen: text.length, tag: el.tagName, classes: el.className };
                }
            }
        }
    }
    
    // Find the element with the most text that ISN'T body/html
    var maxTextEl = null;
    var maxTextLen = 0;
    for (var i = 0; i < allEls.length; i++) {
        var el = allEls[i];
        if (el.tagName === 'BODY' || el.tagName === 'HTML') continue;
        var text = (el.innerText || '').trim();
        if (text.length > maxTextLen) {
            maxTextLen = text.length;
            maxTextEl = {
                tag: el.tagName,
                classes: el.className,
                id: el.id,
                textLen: text.length,
                jsname: el.getAttribute('jsname'),
                role: el.getAttribute('role'),
                dataAttrs: Array.from(el.attributes).filter(a => a.name.startsWith('data-')).map(a => a.name + '=' + a.value)
            };
        }
    }
    
    return JSON.stringify({
        classesWithSubstantialText: classNames,
        dataAttributesOnSubstantialElements: aiAttrs,
        largestTextElement: maxTextEl
    }, null, 2);
    """
    
    analysis = driver.execute_script(js_analysis)
    with open("debug_analysis.json", "w", encoding="utf-8") as f:
        f.write(analysis)
    print("    -> debug_analysis.json saved")
    
    # Also try to find the specific AI content area
    js_find_ai = """
    // Look for elements that might be the AI response container
    // by checking which div has the most paragraph-like text content
    var candidates = [];
    var divs = document.querySelectorAll('div');
    
    for (var i = 0; i < divs.length; i++) {
        var div = divs[i];
        var text = (div.innerText || '').trim();
        if (text.length < 100) continue;
        
        // Count paragraphs and list items inside
        var ps = div.querySelectorAll('p, li, h2, h3');
        if (ps.length < 2) continue;
        
        // This div has structured content - it might be the AI response
        candidates.push({
            tag: div.tagName,
            classes: div.className.substring(0, 100),
            id: div.id,
            textLen: text.length,
            paragraphs: ps.length,
            jsname: div.getAttribute('jsname'),
            role: div.getAttribute('role'),
            firstLine: text.substring(0, 120),
            depth: (function(el) { var d = 0; while(el.parentElement) { d++; el = el.parentElement; } return d; })(div)
        });
    }
    
    // Sort by paragraph count (more = more likely AI content)
    candidates.sort(function(a, b) { return b.paragraphs - a.paragraphs; });
    
    // Return top 15 candidates
    return JSON.stringify(candidates.slice(0, 15), null, 2);
    """
    
    ai_candidates = driver.execute_script(js_find_ai)
    with open("debug_ai_candidates.json", "w", encoding="utf-8") as f:
        f.write(ai_candidates)
    print("    -> debug_ai_candidates.json saved")
    
    # Print the current URL
    print(f"\n[6] Current URL: {driver.current_url}")
    print(f"    Page title: {driver.title}")
    
    # Print first 500 chars of body text
    print(f"\n[7] First 500 chars of body text:")
    print(body_text[:500])
    print("...")
    
    print("\n[DONE] Closing browser...")
    driver.quit()

if __name__ == "__main__":
    run_diagnostic()
