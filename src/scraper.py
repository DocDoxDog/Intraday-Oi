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
    """Raised when the page structure doesn't match what we expect.
    Fail loud — never silently return empty/partial data."""
    pass


def scrape(url: str | None = None) -> dict:
    url = url or os.environ["QUIKSTRIKE_URL"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)  # กัน chart render/AJAX ไม่ทัน

        data = page.evaluate(EXTRACT_JS)
        browser.close()

    if data.get("error"):
        raise ScrapeError(data["error"])

    if not data.get("charts"):
        raise ScrapeError("ไม่พบ chart ใดๆ ในหน้า — session อาจหมดอายุ หรือโครงหน้าเปลี่ยน")

    return data


if __name__ == "__main__":
    import json
    result = scrape()
    print(json.dumps(result, ensure_ascii=False, indent=2))
