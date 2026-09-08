"""
scraper.py
==========
ดึงข้อมูล QuikStrike Vol2Vol Expected Range แบบ Intraday

โครงหน้าใหม่ของ CME ไม่ได้สร้าง Highcharts object ใน DOM แล้ว แต่สร้างภาพ
PNG พร้อม HTML image-map โดยเก็บค่าราย strike ทั้งหมดไว้ใน attribute `fields`.
ฟังก์ชันนี้จึงสั่งเปิดแท็บ Intraday ให้เสร็จก่อน แล้วอ่าน image-map โดยตรง
ซึ่งได้ข้อมูล IV, premium, Greeks, OI, volume, intraday volume และ expected
range ครบกว่าการอ่านข้อความบนหน้าเว็บ.
"""

from __future__ import annotations

import os
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


INTRADAY_SELECTOR = "map area[fields]"
INTRADAY_LINK_ID = "MainContent_ucViewControl_IntegratedV2VExpectedRange_1_lbIntraday"


EXTRACT_INTRADAY_JS = r"""
() => {
    const parseFields = (value) => {
        const out = {};
        for (const item of (value || '').split('~')) {
            const sep = item.indexOf('|');
            if (sep < 0) continue;
            out[item.slice(0, sep)] = item.slice(sep + 1);
        }
        return out;
    };

    const areas = [...document.querySelectorAll('map area')];
    const strikeRows = areas
        .map(a => ({
            coords: a.getAttribute('coords'),
            template_id: a.getAttribute('templateid'),
            fields: parseFields(a.getAttribute('fields')),
        }))
        .filter(x => x.fields.callPremium !== undefined);

    const expectedRanges = areas
        .map(a => ({
            coords: a.getAttribute('coords'),
            fields: parseFields(a.getAttribute('fields')),
        }))
        .filter(x => x.fields.lower !== undefined && x.fields.upper !== undefined)
        .map(x => x.fields);

    const markerText = areas
        .map(a => a.getAttribute('title') || a.getAttribute('alt') || '')
        .filter(Boolean);

    const deltaMarkers = markerText
        .filter(t => /^Delta:/i.test(t))
        .map(t => {
            const delta = t.match(/Delta:\s*([^\n]+)/i);
            const strike = t.match(/Strike:\s*([^\n]+)/i);
            const vol = t.match(/Vol:\s*([^\n]+)/i);
            return {
                delta: delta ? delta[1].trim() : null,
                strike: strike ? strike[1].trim() : null,
                vol: vol ? vol[1].trim() : null,
            };
        });

    const futureMarkers = markerText.filter(t => /Future:/i.test(t));
    const heading = document.querySelector('.viewheader-info h3')?.innerText || '';
    const chart = document.querySelector('img.chart');
    const panel = document.querySelector('[dataobjectid]');

    return {
        mode: 'intraday',
        heading,
        object_id: panel?.getAttribute('dataobjectid') || null,
        chart_image_url: chart ? new URL(chart.getAttribute('src'), location.href).href : null,
        chart_image_width: chart?.naturalWidth || null,
        chart_image_height: chart?.naturalHeight || null,
        strike_rows: strikeRows,
        expected_ranges: expectedRanges,
        future_markers: futureMarkers,
        delta_markers: deltaMarkers,
    };
}
"""


# Fallback สำหรับหน้า/มุมมองเก่าที่สร้าง Highcharts object ไว้ใน DOM
EXTRACT_HIGHCHARTS_JS = r"""
() => {
    const result = { charts: [], source: 'highcharts' };
    if (typeof Highcharts === 'undefined' || !Highcharts.charts) {
        result.error = 'ไม่พบทั้ง QuikStrike image-map และ Highcharts';
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
                })),
            });
        }
        for (const ax of chart.xAxis) {
            chartData.plotLines.push(...(ax.plotLinesAndBands || []).map(pl => ({
                value: pl.options.value,
                label: pl.options.label ? pl.options.label.text : null,
            })));
        }
        result.charts.push(chartData);
    }
    return result;
}
"""


class ScrapeError(Exception):
    pass


def _load_intraday_chart(page) -> None:
    """รอ chart เดิมก่อน แล้ว force postback ไปแท็บ Intraday ถ้ายังไม่มี image-map."""
    try:
        page.wait_for_selector(INTRADAY_SELECTOR, state="attached", timeout=12_000)
        return
    except PlaywrightTimeoutError:
        pass

    link = page.locator(f"#{INTRADAY_LINK_ID}")
    if link.count() == 0:
        raise ScrapeError(
            "ไม่พบแท็บ Intraday หรือ image-map ในหน้า QuikStrike; "
            "หน้าอาจเปลี่ยนโครงสร้างหรือ session หมดอายุ"
        )

    # ลิงก์เป็น ASP.NET __doPostBack; บางรุ่นตอบด้วย full navigation และบางรุ่น
    # ตอบผ่าน submit/XHR โดย URL เดิม จึงไม่ห่อด้วย expect_navigation ซึ่งอาจค้าง
    # จน timeout แม้ postback สำเร็จแล้ว.
    link.click(timeout=10_000)

    try:
        page.wait_for_selector(INTRADAY_SELECTOR, state="attached", timeout=45_000)
    except PlaywrightTimeoutError as exc:
        body = (page.locator("body").inner_text(timeout=5_000) or "")[:1200]
        raise ScrapeError(f"คลิก Intraday แล้วไม่พบข้อมูล chart: {body}") from exc


def scrape(url: str | None = None) -> dict:
    url = url or os.environ.get("QUIKSTRIKE_URL", "")
    if not url:
        raise ScrapeError("QUIKSTRIKE_URL ว่างเปล่า")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(500)
            _load_intraday_chart(page)
            page.wait_for_timeout(500)

            page_text = page.locator("body").inner_text()
            page_heading = None
            heading_locator = page.locator(".viewheader-info h3")
            if heading_locator.count():
                page_heading = heading_locator.first.inner_text()

            chart_data = page.evaluate(EXTRACT_INTRADAY_JS)
            if not chart_data.get("strike_rows"):
                # ใช้ fallback เฉพาะกรณี CME เปลี่ยนกลับไปใช้ Highcharts
                chart_data = page.evaluate(EXTRACT_HIGHCHARTS_JS)
                if chart_data.get("error") or not chart_data.get("charts"):
                    raise ScrapeError(
                        chart_data.get("error")
                        or "ไม่พบข้อมูล strike ใน QuikStrike chart"
                    )

            screenshot = None
            try:
                chart_image = page.locator("img.chart")
                if chart_image.count():
                    screenshot = chart_image.screenshot(type="png")
                else:
                    chart_container = page.locator("#chart")
                    screenshot = chart_container.screenshot(type="png")
            except Exception:
                screenshot = None

            result = {
                "source": "quikstrike_intraday_image_map"
                if chart_data.get("strike_rows")
                else "quikstrike_highcharts_fallback",
                "chart_data": chart_data,
                "page_heading": page_heading,
                "page_text": page_text,
                "screenshot": screenshot,
            }
            return result
        finally:
            browser.close()


if __name__ == "__main__":
    import json

    result = scrape()
    debug = {
        **result,
        "screenshot": (
            f"<{len(result['screenshot'])} bytes>"
            if result.get("screenshot")
            else None
        ),
    }
    print(json.dumps(debug, ensure_ascii=False, indent=2))
