"""
scraper.py
==========
ดึงข้อมูลดิบจาก Highcharts object ในหน้า QuikStrike โดยตรง (ไม่ parse SVG/HTML)
คืนค่าเป็น dict — ให้ parser.py แปลงเป็น schema ต่อไป
"""

import os
from playwright.sync_api import sync_playwright

EXTRACT_JS = """
() => {
    const result = { charts: [] };

    if (typeof Highcharts === 'undefined' || !Highcharts.charts) {
        result.error = "Highcharts global object ไม่พบในหน้านี้ — โครงหน้าอาจเปลี่ยน หรือโหลดไม่ทัน";
        return result;
    }

    for (const chart of Highcharts.charts) {
        if (!chart) continue;

        const chartData = {
            title: chart.title ? chart.title.textStr : null,
            subtitle: chart.subtitle ? chart.subtitle.textStr : null,
            series: [],
            plotLines: [],
        };

        for (const s of chart.series) {
            chartData.series.push({
                name: s.name,
                type: s.type,
                data: s.data.map(pt => ({
                    x: pt.x,
                    y: pt.y,
                    category: pt.category !== undefined ? pt.category : null,
                }))
            });
        }

        for (const ax of chart.xAxis) {
            const lines = (ax.plotLinesAndBands || []).map(pl => ({
                value: pl.options.value,
                label: pl.options.label ? pl.options.label.text : null,
            }));
            chartData.plotLines.push(...lines);
        }

        result.charts.push(chartData);
    }

    return result;
}
"""

class ScrapeError(Exception):
    pass

def scrape(url: str | None = None) -> dict:
    url = url or os.environ.get("QUIKSTRIKE_URL", "")
    if not url:
        raise ScrapeError("QUIKSTRIKE_URL ว่างเปล่า")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000) 

        data = page.evaluate(EXTRACT_JS)

        # DTE ปรากฏใน heading บนสุดของหน้า เช่น
        # "Gold (OG|GC) G2RN6 (0.22 DTE) vs 4115.7 (+33.3) - Intraday Volume"
        # ไม่ใช่ใน Highcharts title/subtitle ของตัว chart เอง
        #
        # เดิมดึงจาก querySelector('h1, h2, .page-title, [class*="title"]') ตัวเดียว —
        # ปัญหาคือ selector แบบ [class*="title"] กว้างเกินไป บางครั้งไปเจอ element อื่น
        # (เช่น tooltip/template ที่ค้างค่า default) ที่ดันมี "(0.00 DTE)" อยู่ในนั้นด้วย
        # ทำให้ parser ไปจับ DTE ผิดตัว ได้ 0.00 เสมอทั้งที่ของจริงไม่ใช่
        #
        # แก้โดยดึง "ทั้งหน้า" (document.body.innerText) แทน แล้วให้ parser.py
        # ใช้ regex ที่ anchor กับบริบทเต็ม "(X DTE) vs Y" เพื่อจับให้ตรงตัวจริงเท่านั้น
        # ไม่พึ่ง selector เดาสุ่มอีกต่อไป
        page_heading = None
        page_text = None
        try:
            page_heading = page.evaluate("""
                () => {
                    const el = document.querySelector('h1, h2, .page-title, [class*="title"]');
                    return el ? el.innerText : document.title;
                }
            """)
        except Exception:
            page_heading = None
        try:
            page_text = page.evaluate("() => document.body.innerText")
        except Exception:
            page_text = None

        screenshot = None
        try:
            chart_el = page.query_selector(".highcharts-container")
            if chart_el:
                screenshot = chart_el.screenshot(type="png")
            else:
                screenshot = page.screenshot(type="png")
        except Exception:
            screenshot = None

        browser.close()

    if data.get("error"):
        raise ScrapeError(data["error"])

    if not data.get("charts"):
        raise ScrapeError("ไม่พบ chart ใดๆ ในหน้า")

    data["screenshot"] = screenshot
    data["page_heading"] = page_heading
    data["page_text"] = page_text
    return data

if __name__ == "__main__":
    import json
    result = scrape()
    debug = {**result, "screenshot": f"<{len(result['screenshot'])} bytes>" if result.get("screenshot") else None}
    print(json.dumps(debug, ensure_ascii=False, indent=2))
    
