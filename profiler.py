"""
PROFILER: Measures exact per-phase timing of the scraper pipeline.
Runs 3 queries and reports detailed breakdown in milliseconds.
"""
import time
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

AI_CONTENT_SELECTORS = [
    "#aim-chrome-initial-inline-async-container",
    "div[data-xid='aim-mars-turn-root']",
    "div.tonYlb.Uphzyf",
    "div.qJYHHd.mp0vvc",
    "div.WzWwpc.vve6Ce",
    "div.SLPe5b",
    "div.bzXtMb",
]

QUERIES = [
    "What is Kubernetes",
    "Explain microservices architecture",
    "What is Redis cache",
]

def profile():
    # ── PHASE 0: Browser launch ──
    t0 = time.perf_counter()
    opts = ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,900")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--lang=en-US")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=opts)
    driver.implicitly_wait(2)
    t_browser = time.perf_counter() - t0
    print(f"\n{'='*70}")
    print(f"  BROWSER LAUNCH: {t_browser*1000:.0f}ms")
    print(f"{'='*70}\n")

    for qi, query in enumerate(QUERIES, 1):
        print(f"── Query {qi}/{len(QUERIES)}: \"{query}\" ──")
        timings = {}

        # ── PHASE 1: URL construction ──
        t1 = time.perf_counter()
        encoded_q = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_q}&udm=50"
        timings["url_build"] = (time.perf_counter() - t1) * 1000

        # ── PHASE 2: Navigation (driver.get) ──
        t2 = time.perf_counter()
        driver.get(url)
        timings["navigation"] = (time.perf_counter() - t2) * 1000

        # ── PHASE 3: Wait for AI container to appear ──
        t3 = time.perf_counter()
        container_found = False
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#aim-chrome-initial-inline-async-container")
                )
            )
            container_found = True
        except TimeoutException:
            pass
        timings["container_wait"] = (time.perf_counter() - t3) * 1000

        # ── PHASE 4: Fixed sleep (current: 2s) ──
        t4 = time.perf_counter()
        time.sleep(2)
        timings["fixed_sleep"] = (time.perf_counter() - t4) * 1000

        # ── PHASE 5: Stability polling loop ──
        t5 = time.perf_counter()
        last_text = ""
        stable_count = 0
        poll_count = 0
        final_text = ""

        while (time.perf_counter() - t5) < 55:
            poll_count += 1
            # Quick scrape
            scraped = ""
            for sel in AI_CONTENT_SELECTORS:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        try:
                            t = el.text.strip()
                            if t and len(t) > 50:
                                scraped = t
                                break
                        except StaleElementReferenceException:
                            continue
                except:
                    continue
                if scraped:
                    break

            if scraped and len(scraped) > 30:
                if scraped == last_text:
                    stable_count += 1
                    if stable_count >= 3:
                        final_text = scraped
                        break
                else:
                    stable_count = 0
                    last_text = scraped

            time.sleep(0.8)

        timings["polling"] = (time.perf_counter() - t5) * 1000
        timings["poll_iterations"] = poll_count

        # ── PHASE 6: Text cleaning ──
        t6 = time.perf_counter()
        noise_exact = {
            "accessibility links", "skip to main content", "accessibility help",
            "accessibility feedback", "filters and topics", "ai mode", "all",
            "images", "videos", "shopping", "news", "more", "sign in",
            "search results", "show all",
        }
        noise_contains = [
            "ai can make mistakes", "double-check responses",
            "you can now share this thread", "quick results from the web:",
        ]
        lines = final_text.split("\n")
        cleaned = []
        content_started = False
        for line in lines:
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if low in noise_exact:
                continue
            if any(n in low for n in noise_contains):
                continue
            if not content_started and len(s) > 40:
                content_started = True
            if not content_started and len(s) < 30:
                continue
            cleaned.append(s)
        cleaned_text = "\n".join(cleaned).strip()
        timings["cleaning"] = (time.perf_counter() - t6) * 1000

        total = sum(v for k, v in timings.items() if k != "poll_iterations")

        # ── Report ──
        print(f"  Container found: {container_found}")
        print(f"  Response length:  {len(cleaned_text)} chars")
        print(f"  Poll iterations:  {int(timings['poll_iterations'])}")
        print()
        print(f"  {'Phase':<25} {'Time':>10}")
        print(f"  {'─'*25} {'─'*10}")
        print(f"  {'URL build':<25} {timings['url_build']:>8.1f}ms")
        print(f"  {'Navigation (driver.get)':<25} {timings['navigation']:>8.0f}ms")
        print(f"  {'Container wait':<25} {timings['container_wait']:>8.0f}ms")
        print(f"  {'Fixed sleep (2s)':<25} {timings['fixed_sleep']:>8.0f}ms")
        print(f"  {'Stability polling':<25} {timings['polling']:>8.0f}ms")
        print(f"  {'Text cleaning':<25} {timings['cleaning']:>8.2f}ms")
        print(f"  {'─'*25} {'─'*10}")
        print(f"  {'TOTAL':<25} {total:>8.0f}ms  ({total/1000:.1f}s)")

        # Identify the biggest time sink
        phases = {k: v for k, v in timings.items() if k != "poll_iterations"}
        biggest = max(phases, key=phases.get)
        print(f"\n  >> BOTTLENECK: {biggest} ({phases[biggest]:.0f}ms)")
        print()

    # ── Measure implicit wait impact ──
    print(f"{'='*70}")
    print("  IMPLICIT WAIT IMPACT TEST")
    print(f"{'='*70}")

    # Test finding a non-existent element with current implicit wait
    t_imp = time.perf_counter()
    try:
        driver.find_elements(By.CSS_SELECTOR, "#nonexistent-element-xyz-12345")
    except:
        pass
    implicit_cost = (time.perf_counter() - t_imp) * 1000
    print(f"  find_elements (missing element): {implicit_cost:.0f}ms")
    print(f"  Current implicit wait: {driver.timeouts.implicit_wait}ms")

    # Test with 0 implicit wait
    driver.implicitly_wait(0)
    t_imp2 = time.perf_counter()
    try:
        driver.find_elements(By.CSS_SELECTOR, "#nonexistent-element-xyz-12345")
    except:
        pass
    zero_cost = (time.perf_counter() - t_imp2) * 1000
    print(f"  find_elements (0 implicit wait): {zero_cost:.0f}ms")
    driver.implicitly_wait(2)

    # ── Measure selector speed comparison ──
    print(f"\n{'='*70}")
    print("  SELECTOR SPEED COMPARISON (current page)")
    print(f"{'='*70}")
    for sel in AI_CONTENT_SELECTORS:
        t_sel = time.perf_counter()
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            found = len(els)
        except:
            found = -1
        elapsed_sel = (time.perf_counter() - t_sel) * 1000
        print(f"  {sel:<55} {elapsed_sel:>6.1f}ms  (found: {found})")

    # JS scrape speed
    t_js = time.perf_counter()
    try:
        driver.execute_script("""
        var el = document.querySelector('#aim-chrome-initial-inline-async-container');
        return el ? el.innerText : '';
        """)
    except:
        pass
    js_cost = (time.perf_counter() - t_js) * 1000
    print(f"\n  JS getElementById equivalent:    {js_cost:>6.1f}ms")

    driver.quit()
    print(f"\n{'='*70}")
    print("  PROFILING COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    profile()
