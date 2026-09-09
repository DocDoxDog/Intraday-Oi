"""
scraper.py
==========
ดึงข้อมูล QuikStrike Open Interest View

โครงหน้าใหม่ของ CME ไม่ได้สร้าง Highcharts object ใน DOM แล้ว แต่สร้างภาพ
PNG พร้อม HTML image-map โดยเก็บค่าราย strike ทั้งหมดไว้ใน attribute `fields`.
ฟังก์ชันนี้ใช้ chart Open Interest/EOD ที่เปิดให้ใช้ฟรี แล้วอ่าน image-map
โดยตรง. Intraday volume และ Expected Range อาจไม่มีใน free tier จึงไม่ควร
เรียก OI ว่า Intraday volume หรือสร้างค่าดังกล่าวขึ้นมาเอง.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


OI_SELECTOR = "map area[fields]"
INTRADAY_LINK_ID = "MainContent_ucViewControl_IntegratedV2VExpectedRange_1_lbIntraday"
OI_LINK_ID = "MainContent_ucViewControl_IntegratedV2VExpectedRange_lbOI"
EXPIRATION_LINK_SELECTOR = "a[id*='ucExpirationGroup'][id$='lbExpiration']"
QUIKSTRIKE_REFERER = "https://www.cmegroup.com/tools-information/quikstrike/vol2vol-expected-range.html"
QUIKSTRIKE_SESSION_STATE = os.environ.get("QUIKSTRIKE_SESSION_STATE", "/tmp/quikstrike_storage_state.json")


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
        mode: 'open_interest',
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


def _select_preferred_expiration(page) -> dict:
    """เลือก Gold option expiry ตาม policy ของงานนี้.

    ปกติเลือก Gold Options Friday expiry (`OG<number><month><year>`) ที่มี DTE
    เป็นบวกน้อยที่สุด ซึ่งคือวันศุกร์ถัดไปและไม่ใช่ 0DTE Futures รายวัน. ในสัปดาห์
    สุดท้ายของเดือน ให้เลือก standard monthly Gold Options (`OG<month><year>`)
    ของเดือนปัจจุบันแทน weekly.
    """
    links = page.locator(EXPIRATION_LINK_SELECTOR)
    candidates = []
    for i in range(links.count()):
        link = links.nth(i)
        try:
            code = (link.locator(".item-name").inner_text() or "").strip()
            text = link.inner_text() or ""
        except Exception:
            continue
        if not code.startswith("OG"):
            continue
        match = re.search(r"\(([0-9]+(?:\.[0-9]+)?)\s*DTE\)", text, re.I)
        if not match:
            continue
        dte = float(match.group(1))
        if dte <= 0.5:
            continue
        weekly_friday = bool(re.match(r"^OG\d+[A-Z]\d$", code, re.I))
        monthly = bool(re.match(r"^OG[A-Z]\d$", code, re.I))
        if weekly_friday or monthly:
            candidates.append({"link": link, "code": code, "dte": dte, "weekly": weekly_friday, "monthly": monthly})

    if not candidates:
        return {"selected": None, "policy": "no_positive_gold_expiry_found"}

    now = datetime.now(timezone(timedelta(hours=7))).date()
    next_friday = now + timedelta(days=(4 - now.weekday()) % 7)
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    last_friday = month_end - timedelta(days=(month_end.weekday() - 4) % 7)
    last_week = next_friday >= last_friday

    if last_week:
        monthly = [x for x in candidates if x["monthly"]]
        if monthly:
            expected = max(0, (last_friday - now).days)
            chosen = min(monthly, key=lambda x: abs(x["dte"] - expected))
            policy = "current_month_end_monthly_options_last_week"
        else:
            chosen = min(candidates, key=lambda x: x["dte"])
            policy = "weekly_options_fallback_no_monthly_series"
    else:
        weekly = [x for x in candidates if x["weekly"]]
        chosen = min(weekly or candidates, key=lambda x: x["dte"])
        policy = "next_friday_weekly_options"

    selected = chosen["code"]
    current_heading = page.locator(".viewheader-info h3").first.inner_text() if page.locator(".viewheader-info h3").count() else ""
    if selected not in current_heading:
        try:
            target_link = chosen["link"]
            if not target_link.is_visible():
                trigger = page.locator("#ctl00_ucSelector_hlExpiration")
                if trigger.count():
                    trigger.click(timeout=10_000)
                    page.wait_for_timeout(250)
            # Expiration links live inside a hidden popup; force the ASP.NET
            # postback click rather than relying on popup visibility.
            target_link.click(force=True, timeout=10_000)
            # This postback is a full reload in some QuikStrike deployments
            # and an async update in others. A short polling loop handles both
            # without relying on a navigation event that can be missed.
            for _ in range(30):
                page.wait_for_timeout(1_000)
                heading = page.locator(".viewheader-info h3").first.inner_text() if page.locator(".viewheader-info h3").count() else ""
                if selected in heading:
                    break
            else:
                raise ScrapeError(f"postback แล้วแต่ heading ไม่เปลี่ยนเป็น {selected}")
        except Exception as exc:
            raise ScrapeError(f"เลือก expiration {selected} ไม่สำเร็จ: {exc}") from exc
    return {"selected": selected, "policy": policy, "dte_hint": chosen["dte"]}


def _load_oi_chart(page) -> None:
    """คลิก OI tab ที่ยังเปิดให้ใช้ฟรี แล้วรอ chart โหลด."""
    oi_link = page.locator(f"#{OI_LINK_ID}")
    if oi_link.count():
        try:
            oi_link.click(force=True, timeout=15_000)
            page.wait_for_timeout(2_000)
        except Exception:
            pass
    try:
        # ResizerPanel loads Chart.aspx asynchronously; GitHub Actions runners
        # are often slower than local Chromium, so give the first chart up to
        # 35 seconds to appear before deciding that a postback is necessary.
        page.wait_for_selector(OI_SELECTOR, state="attached", timeout=35_000)
        return
    except PlaywrightTimeoutError:
        pass

    # Some free-tier pages render the OI chart as Highcharts rather than an
    # image-map. Let scrape() use its Highcharts fallback instead of trying to
    # click the unavailable Intraday tab.
    return


def _read_highcharts(page) -> dict:
    return page.evaluate(EXTRACT_HIGHCHARTS_JS)


def _read_secondary_oi_views(page) -> dict:
    """อ่าน OI Change และ Churn ที่ยังมีใน free view โดยไม่เรียกเป็น volume."""
    views = {
        "oi_change": "MainContent_ucViewControl_IntegratedV2VExpectedRange_lbOIChg",
        "churn": "MainContent_ucViewControl_IntegratedV2VExpectedRange_lbChurn",
    }
    out = {}
    for name, element_id in views.items():
        link = page.locator(f"#{element_id}")
        if not link.count():
            continue
        try:
            link.click(force=True, timeout=15_000)
            page.wait_for_timeout(2_000)
            data = _read_highcharts(page)
            if data.get("charts"):
                out[name] = data
        except Exception:
            continue
    return out


def scrape(url: str | None = None) -> dict:
    url = url or os.environ.get("QUIKSTRIKE_URL", "")
    if not url:
        raise ScrapeError("QUIKSTRIKE_URL ว่างเปล่า")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context_options = {
            "viewport": {"width": 1600, "height": 1000},
            "extra_http_headers": {"Referer": QUIKSTRIKE_REFERER},
        }
        if os.path.exists(QUIKSTRIKE_SESSION_STATE):
            context_options["storage_state"] = QUIKSTRIKE_SESSION_STATE
        context = browser.new_context(**context_options)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(500)
            expiration_selection = _select_preferred_expiration(page)
            _load_oi_chart(page)
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

            secondary_views = _read_secondary_oi_views(page)
            # Return to the primary OI view before capturing the image sent to Telegram.
            oi_link = page.locator(f"#{OI_LINK_ID}")
            if oi_link.count():
                try:
                    oi_link.click(force=True, timeout=15_000)
                    page.wait_for_timeout(2_000)
                except Exception:
                    pass

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
                "source": "quikstrike_open_interest_image_map"
                if chart_data.get("strike_rows")
                else "quikstrike_highcharts_fallback",
                "chart_data": chart_data,
                "secondary_views": secondary_views,
                "expiration_selection": expiration_selection,
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
