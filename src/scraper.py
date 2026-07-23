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
    