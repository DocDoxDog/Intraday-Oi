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
EXPIRATION_LINK_SELECTOR = "a[id*='lvExpirations'][id$='lbExpiration']"
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
        # Some QuikStrike renders expose the active expiration only in the
        # heading while the selector entries are populated later. The active
        # heading is still authoritative for this snapshot, so use it rather
        # than rejecting a valid current contract.
        try:
            heading = page.locator(".viewheader-info h3").first.inner_text()
        except Exception:
            heading = ""
        match = re.search(
            r"(?P<code>[A-Za-z0-9._-]+)\s*\((?P<dte>[0-9]+(?:\.[0-9]+)?)\s*DTE\)",
            heading,
            re.I,
        )
        if match:
            dte = float(match.group("dte"))
            code = match.group("code")
            if dte > 0:
                return {
                    "selected": code,
                    "policy": "active_heading_fallback",
                    "dte_hint": dte,
                }
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
                if chart_image.count() and chart_image.first.is_visible():
                    screenshot = chart_image.first.screenshot(type="png")
                else:
                    chart_container = page.locator("#chart")
                    if chart_container.count() and chart_container.first.is_visible():
                        screenshot = chart_container.first.screenshot(type="png")
            except Exception:
                screenshot = None

            # Last-resort source capture: the actual rendered QuikStrike page.
            if not screenshot:
                try:
                    screenshot = page.screenshot(
                        type="png", full_page=False, animations="disabled"
                    )
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



def _chart_fingerprint(page) -> str:
    """Fingerprint the currently rendered OI surface.

    QuikStrike may leave the previous image-map attached while an expiration
    postback is still updating. We must prove the chart changed before storing
    it under the new expiration identity.
    """
    return page.evaluate("""
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
        const areas = [...document.querySelectorAll('map area[fields]')];
        const rows = areas
            .map(a => parseFields(a.getAttribute('fields')))
            .filter(f => f.oiCall !== undefined || f.oiPut !== undefined);
        const sample = rows.slice(0, 3).map(f => ({
            title: f.title || null,
            call: f.oiCall || null,
            put: f.oiPut || null,
            total: f.oiTotal || null
        }));
        const chart = document.querySelector('img.chart');
        return JSON.stringify({
            heading: document.querySelector('.viewheader-info h3')?.innerText || '',
            object_id: document.querySelector('[dataobjectid]')?.getAttribute('dataobjectid') || '',
            count: rows.length,
            sample,
            src: chart?.getAttribute('src') || ''
        });
    }
    """)


def _open_expiration_menu(page) -> None:
    """Open the rendered expiration selector before discovering its entries."""
    triggers = [
        page.locator("#ctl00_ucSelector_hlExpiration"),
        page.get_by_text(re.compile(r"^\\s*EXPIRATION\\s*:?\\s*$", re.I)),
        page.locator("[aria-label*='expiration' i]"),
        page.locator("[title*='expiration' i]"),
        page.get_by_text("Expiration", exact=True),
        page.get_by_text("Expirations", exact=True),
    ]
    for trigger in triggers:
        try:
            if trigger.count() and trigger.first.is_visible():
                trigger.first.click(timeout=5_000, force=True)
                page.wait_for_timeout(1_500)
                return
        except Exception:
            continue


def _extract_dte(text: str) -> float | None:
    """Accept the common QuikStrike renderings: '(12.5 DTE)' or 'DTE: 12.5'."""
    patterns = (
        r"\(([0-9]+(?:\.[0-9]+)?)\s*DTE\)",
        r"\bDTE\s*[:=-]?\s*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return None


def _expiration_code_from_text(text: str, dte_match: re.Match[str] | None = None) -> str:
    """Recover an option code from visible anchor text without assuming OG."""
    if not text:
        return ""
    prefix = text[:dte_match.start()] if dte_match else text
    tokens = re.findall(r"[A-Za-z0-9._-]+", prefix)
    for token in reversed(tokens):
        if re.search(r"[A-Za-z]", token) and re.search(r"\d", token) and 2 <= len(token) <= 20:
            return token
    return ""


def _discover_gold_expirations(page, limit: int = 7) -> list[dict]:
    """Discover real expiration identities from the live selector.

    The selector itself is authoritative. Do not depend on one ASP.NET control
    ID or on the historical '(xx DTE)' formatting; both have changed across
    QuikStrike renders.
    """
    _open_expiration_menu(page)

    links = page.locator(EXPIRATION_LINK_SELECTOR)
    if links.count() == 0:
        # The current CME render can expose the dropdown as buttons/options
        # rather than anchors. Search only interactive expiration entries.
        links = page.locator("a,button,[role='option'],[role='menuitem'],li")
    if links.count() == 0:
        links = page.locator("a")

    candidates = []
    seen = set()
    for i in range(links.count()):
        link = links.nth(i)
        try:
            text = (link.inner_text() or "").strip()
            title = (link.get_attribute("title") or "").strip()
        except Exception:
            continue

        # Current QuikStrike puts DTE and Option Symbol in the anchor title,
        # while the visible label shows only code/date.
        metadata = "\n".join(x for x in (text, title) if x)
        if not metadata or ("DTE" not in metadata.upper() and "OPTION EXPIRATION" not in metadata.upper()):
            continue

        dte = _extract_dte(metadata)
        if dte is None or dte <= 0:
            continue

        try:
            code = (link.locator(".item-name").inner_text() or "").strip()
        except Exception:
            code = ""
        if not code:
            match = re.search(r"Option Symbol:\s*([A-Za-z0-9._-]+)", metadata, re.I)
            code = match.group(1).strip() if match else ""
        if not code:
            code = _expiration_code_from_text(metadata, re.search(
                r"(?:(?:\([0-9]+(?:\.[0-9]+)?)\s*DTE\))|(?:DTE\s*[:=-]?\s*[0-9]+(?:\.[0-9]+)?)",
                metadata, re.I,
            ))
        code = code.strip()
        if not code or code.upper() in seen:
            continue

        seen.add(code.upper())
        candidates.append({"code": code, "dte": dte})

    candidates.sort(key=lambda x: (x["dte"], x["code"]))
    if candidates:
        return candidates[: max(1, int(limit))]

    # Fallback: the active expiration is always present in the report heading,
    # even when the selector menu itself is lazy-rendered. Keep this as a real
    # single-expiry snapshot rather than inventing additional expirations.
    heading = ""
    try:
        heading = page.locator(".viewheader-info h3").first.inner_text()
    except Exception:
        pass
    match = re.search(
        r"(?P<code>[A-Za-z0-9._-]+)\s*\((?P<dte>[0-9]+(?:\.[0-9]+)?)\s*DTE\)",
        heading,
        re.I,
    )
    if match:
        dte = float(match.group("dte"))
        code = match.group("code")
        if dte > 0:
            print(
                f"⚠️  QuikStrike expiration menu ไม่ถูก render; ใช้ active heading fallback "
                f"{code} ({dte} DTE)"
            )
            return [{"code": code, "dte": dte}]
    dte_lines = []
    try:
        body_text = page.locator("body").inner_text()
        dte_lines = [line.strip() for line in body_text.splitlines() if "DTE" in line.upper()][:12]
    except Exception:
        pass
    anchor_count = page.locator("a").count()
    raise ScrapeError(
        "ไม่พบ Gold expirations ที่มี DTE"
        f" | heading={heading!r} | anchors={anchor_count}"
        f" | DTE_text={dte_lines!r}"
    )

def _activate_expiration(page, code: str) -> None:
    # When discovery had to use the active heading fallback, this code is
    # already selected. Do not scan 100+ unrelated anchors; missing selectors
    # can make per-anchor locator calls wait and exhaust the CI timeout.
    try:
        heading = page.locator(".viewheader-info h3").first.inner_text()
    except Exception:
        heading = ""
    if code and code in heading:
        return

    links = page.locator(EXPIRATION_LINK_SELECTOR)
    if links.count() == 0:
        links = page.locator("a,button,[role='option'],[role='menuitem'],li")
    if links.count() == 0:
        links = page.locator("a")
    target = None
    for i in range(links.count()):
        link = links.nth(i)
        try:
            text = (link.inner_text() or "").strip()
            title = (link.get_attribute("title") or "").strip()
            candidate = (link.locator(".item-name").inner_text() or "").strip()
        except Exception:
            continue
        metadata = "\n".join(x for x in (text, title) if x)
        if not candidate:
            match = re.search(r"Option Symbol:\s*([A-Za-z0-9._-]+)", metadata, re.I)
            candidate = match.group(1).strip() if match else ""
        if not candidate and metadata:
            # Same fallback identity rule used during discovery.
            tokens = re.findall(r"[A-Za-z0-9._-]+", metadata)
            for token in reversed(tokens):
                if re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
                    candidate = token
                    break
        if candidate == code:
            target = link
            break
    if target is None:
        raise ScrapeError(f"ไม่พบ expiration {code}")

    before = _chart_fingerprint(page)
    # The first candidate may already be the active expiration. In that case
    # the existing chart is the correct chart and no postback is needed.
    if code in before:
        return
    try:
        trigger = page.locator("#ctl00_ucSelector_hlExpiration")
        if trigger.count() and not target.is_visible():
            trigger.click(timeout=10_000)
            page.wait_for_timeout(250)
        target.click(force=True, timeout=10_000)
        last_heading = ""
        for _ in range(45):
            page.wait_for_timeout(1_000)
            heading = (
                page.locator(".viewheader-info h3").first.inner_text()
                if page.locator(".viewheader-info h3").count()
                else ""
            )
            current = _chart_fingerprint(page)
            if code in heading and current != before:
                return
            last_heading = heading
    except Exception as exc:
        raise ScrapeError(f"เลือก expiration {code} ไม่สำเร็จ: {exc}") from exc
    raise ScrapeError(
        f"expiration {code} เปลี่ยน heading เป็น '{last_heading}' แต่ OI chart "
        "ยังไม่เปลี่ยนจาก snapshot เดิม — หยุดเพื่อป้องกันการติดป้ายข้อมูลผิด"
    )

def scrape_multi_expiration(url: str | None = None, limit: int = 7) -> dict:
    """Scrape several real Gold expirations in one browser session.

    The first snapshot remains compatible with scrape()/parse(). Additional
    snapshots are returned under expiration_snapshots and are not collapsed
    into a single synthetic DTE.
    """
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
            print("[scrape] goto QuikStrike...", flush=True)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(500)
            print("[scrape] discovering expirations...", flush=True)
            candidates = _discover_gold_expirations(page, limit=limit)
            print(f"[scrape] discovered {len(candidates)} expiration(s): {[x['code'] for x in candidates]}", flush=True)
            if not candidates:
                raise ScrapeError("ไม่พบ Gold expirations ที่มี DTE")

            snapshots = []
            for index, candidate in enumerate(candidates):
                print(f"[scrape] activating {candidate['code']} ({candidate['dte']} DTE)...", flush=True)
                _activate_expiration(page, candidate["code"])
                print(f"[scrape] loading OI for {candidate['code']}...", flush=True)
                _load_oi_chart(page)
                page.wait_for_timeout(500)
                chart_data = page.evaluate(EXTRACT_INTRADAY_JS)
                if not chart_data.get("strike_rows"):
                    chart_data = page.evaluate(EXTRACT_HIGHCHARTS_JS)
                if chart_data.get("error") or (
                    not chart_data.get("strike_rows") and not chart_data.get("charts")
                ):
                    raise ScrapeError(
                        f"ไม่พบข้อมูล strike สำหรับ expiration {candidate['code']}"
                    )

                heading_locator = page.locator(".viewheader-info h3")
                heading = (
                    heading_locator.first.inner_text()
                    if heading_locator.count()
                    else ""
                )
                if candidate["code"] not in heading:
                    raise ScrapeError(
                        f"expiration identity mismatch: requested={candidate['code']} heading={heading!r}"
                    )

                source_screenshot = None
                if index == 0:
                    try:
                        chart_image = page.locator("img.chart")
                        if chart_image.count() and chart_image.first.is_visible():
                            source_screenshot = chart_image.first.screenshot(type="png")
                        else:
                            chart_container = page.locator("#chart")
                            if chart_container.count() and chart_container.first.is_visible():
                                source_screenshot = chart_container.first.screenshot(type="png")
                    except Exception:
                        source_screenshot = None

                    # Last-resort source capture: this is still the real QuikStrike
                    # viewport, never a synthetic chart. Keeping it as a source
                    # screenshot is preferable to silently sending no source image.
                    if not source_screenshot:
                        try:
                            source_screenshot = page.screenshot(
                                type="png", full_page=False, animations="disabled"
                            )
                        except Exception:
                            source_screenshot = None

                snapshot = {
                    "source": (
                        "quikstrike_open_interest_image_map"
                        if chart_data.get("strike_rows")
                        else "quikstrike_highcharts_fallback"
                    ),
                    "chart_data": chart_data,
                    "secondary_views": {},
                    "expiration_selection": {
                        "selected": candidate["code"],
                        "policy": "multi_expiry_term_structure",
                        "dte_hint": candidate["dte"],
                    },
                    "page_heading": heading,
                    "page_text": page.locator("body").inner_text(),
                    "screenshot": source_screenshot,
                    "source_screenshot": source_screenshot,
                }

                snapshots.append(snapshot)

            primary = dict(snapshots[0])
            primary["expiration_snapshots"] = snapshots
            primary["multi_expiration"] = {
                "enabled": True,
                "count": len(snapshots),
                "codes": [item["expiration_selection"]["selected"] for item in snapshots],
            }
            return primary
        finally:
            browser.close()
