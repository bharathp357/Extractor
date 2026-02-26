"""
DOM Diagnostic Tool — discover actual CSS selectors on AI provider pages.

Usage:
    python dom_diagnose.py [provider]
    python dom_diagnose.py gemini
    python dom_diagnose.py chatgpt
    python dom_diagnose.py google
    python dom_diagnose.py all       (default)

Opens Chrome with your persistent profile, navigates to each provider,
and dumps DOM info to help debug/update selectors.
"""
import sys
import time
import json
from providers.browser_manager import get_browser_manager
import config


# ── Selectors to probe per provider ──
PROVIDER_PROBES = {
    "google": {
        "url": "https://www.google.com/search?q=hello&udm=50",
        "input_selectors": [
            "textarea[name='q']",
            "textarea.follow-up",
            "div[contenteditable='true']",
            "input[name='q']",
        ],
        "response_selectors": [
            "#aim-chrome-initial-inline-async-container",
            ".aim-card",
            "div[data-xid='aim-mars-turn-root']",
            ".ai-overview-card",
            "div.response",
        ],
        "extra_js": """
            // Check for AI Mode specific containers
            var containers = document.querySelectorAll('[data-xid]');
            var xids = [];
            containers.forEach(function(c) {
                xids.push(c.getAttribute('data-xid') + ' -> ' + c.tagName + '.' + c.className.split(' ').slice(0,2).join('.'));
            });
            return JSON.stringify({xid_elements: xids.slice(0, 20)});
        """,
    },
    "gemini": {
        "url": config.GEMINI_URL,
        "input_selectors": [
            "div.ql-editor[contenteditable='true']",
            "rich-textarea div[contenteditable='true']",
            "div[contenteditable='true'][aria-label*='prompt']",
            "div[contenteditable='true'][role='textbox']",
            "div.input-area-container textarea",
            "textarea[aria-label*='prompt']",
            "div[contenteditable='true']",
            "rich-textarea",
            ".text-input-field",
            "div.input-area",
        ],
        "response_selectors": [
            "message-content.model-response-text",
            "message-content .markdown",
            "model-response .markdown",
            ".response-container-content",
            ".markdown-main-panel",
            "div[data-test-id='response-content']",
        ],
        "extra_js": """
            // Check for custom elements (Gemini uses Web Components)
            var customs = [];
            var allEls = document.querySelectorAll('*');
            for (var i = 0; i < allEls.length && customs.length < 30; i++) {
                var tag = allEls[i].tagName.toLowerCase();
                if (tag.includes('-') && customs.indexOf(tag) < 0) {
                    customs.push(tag);
                }
            }
            // Check for contenteditable
            var editables = document.querySelectorAll('[contenteditable="true"]');
            var editInfo = [];
            editables.forEach(function(e) {
                editInfo.push(e.tagName + '.' + e.className.split(' ').slice(0,2).join('.') +
                    ' | aria=' + (e.getAttribute('aria-label') || 'none') +
                    ' | role=' + (e.getAttribute('role') || 'none'));
            });
            return JSON.stringify({custom_elements: customs, contenteditable: editInfo});
        """,
    },
    "chatgpt": {
        "url": config.CHATGPT_URL,
        "input_selectors": [
            "#prompt-textarea",
            "textarea[data-id='root']",
            "div#prompt-textarea[contenteditable='true']",
            "div[contenteditable='true'][data-placeholder*='Message']",
            "textarea[placeholder*='Message']",
            "div[id='prompt-textarea']",
        ],
        "response_selectors": [
            "div[data-message-author-role='assistant']",
            "div[data-message-author-role='assistant'] .markdown",
            "div.agent-turn",
            ".markdown.prose",
            "div[data-testid*='conversation-turn']",
        ],
        "extra_js": """
            // Check for ProseMirror or special editors
            var editors = document.querySelectorAll('.ProseMirror, [contenteditable="true"], textarea');
            var editorInfo = [];
            editors.forEach(function(e) {
                editorInfo.push({
                    tag: e.tagName,
                    id: e.id || 'none',
                    class: e.className.toString().slice(0, 80),
                    contenteditable: e.getAttribute('contenteditable'),
                    placeholder: e.getAttribute('placeholder') || e.getAttribute('data-placeholder') || 'none',
                    visible: e.offsetHeight > 0
                });
            });
            // Check for send button
            var buttons = document.querySelectorAll('button');
            var sendBtns = [];
            buttons.forEach(function(b) {
                var label = b.getAttribute('aria-label') || b.getAttribute('data-testid') || '';
                if (label.toLowerCase().includes('send') || label.toLowerCase().includes('submit')) {
                    sendBtns.push({label: label, testid: b.getAttribute('data-testid') || 'none', enabled: !b.disabled});
                }
            });
            return JSON.stringify({editors: editorInfo, send_buttons: sendBtns});
        """,
    },
}


def diagnose_provider(bm, provider_name: str):
    """Diagnose a single provider's DOM."""
    probe = PROVIDER_PROBES.get(provider_name)
    if not probe:
        print(f"[!] Unknown provider: {provider_name}")
        return

    print(f"\n{'='*60}")
    print(f"  DIAGNOSING: {provider_name.upper()}")
    print(f"  URL: {probe['url']}")
    print(f"{'='*60}")

    driver = bm.driver

    # Navigate
    if not bm.has_tab(provider_name):
        bm.open_tab(provider_name, probe["url"])
    else:
        bm.switch_to(provider_name)
        driver.get(probe["url"])

    time.sleep(3)
    print(f"\n  Current URL: {driver.current_url}")
    print(f"  Title: {driver.title}")

    # Test input selectors
    print(f"\n  ── Input Selectors ──")
    for sel in probe["input_selectors"]:
        try:
            els = driver.find_elements("css selector", sel)
            visible = [e for e in els if e.is_displayed()]
            if els:
                info = f"  ✓ {sel}"
                info += f"  ({len(els)} found, {len(visible)} visible)"
                if visible:
                    el = visible[0]
                    info += f"  tag={el.tag_name} editable={el.get_attribute('contenteditable')}"
                print(info)
            else:
                print(f"  ✗ {sel}  (not found)")
        except Exception as e:
            print(f"  ✗ {sel}  (error: {e})")

    # Test response selectors
    print(f"\n  ── Response Selectors ──")
    for sel in probe["response_selectors"]:
        try:
            els = driver.find_elements("css selector", sel)
            visible = [e for e in els if e.is_displayed()]
            if els:
                text_preview = ""
                if visible:
                    text_preview = (visible[-1].text or "")[:80].replace("\n", " ")
                print(f"  ✓ {sel}  ({len(els)} found, {len(visible)} visible)")
                if text_preview:
                    print(f"      Preview: \"{text_preview}...\"")
            else:
                print(f"  ✗ {sel}  (not found)")
        except Exception as e:
            print(f"  ✗ {sel}  (error: {e})")

    # Run extra JS diagnostics
    if "extra_js" in probe:
        print(f"\n  ── Extra JS Diagnostics ──")
        try:
            result = driver.execute_script(probe["extra_js"])
            data = json.loads(result) if isinstance(result, str) else result
            print(json.dumps(data, indent=4))
        except Exception as e:
            print(f"  Error running JS: {e}")


def main():
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    providers = list(PROVIDER_PROBES.keys()) if target == "all" else [target]

    print("╔══════════════════════════════════════════════╗")
    print("║     DOM Diagnostic Tool — AI Command Center  ║")
    print("╚══════════════════════════════════════════════╝")

    bm = get_browser_manager()
    bm.launch()

    for p in providers:
        if p in PROVIDER_PROBES:
            diagnose_provider(bm, p)
        else:
            print(f"[!] Unknown provider: {p}")
            print(f"    Available: {', '.join(PROVIDER_PROBES.keys())}")

    print(f"\n{'='*60}")
    print("  Diagnosis complete. Browser left open for manual inspection.")
    print("  Press Ctrl+C to exit.")
    print(f"{'='*60}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
