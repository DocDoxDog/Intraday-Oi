"""
url_manager.py
==============
จัดการ QUIKSTRIKE_URL แบบ self-healing — ไม่ต้องแก้ URL ด้วยมือทุกครั้งที่ qsid หมดอายุ

Retry ladder (เรียงตามลำดับที่ get_url() ลอง):
1. URL ที่เคยเซฟไว้ใน Supabase (public.app_config) — ถ้า validate() ผ่าน ใช้เลย
2. QUIKSTRIKE_URL จาก env/Secret — ถ้า validate() ผ่าน ใช้แล้วเซฟทับของเก่า
3. discover() — เปิด QuikStrike ตั้งแต่ entry point ที่ไม่ต้องมี qsid ล่วงหน้า
   (bootstrap URL ที่มี userId/jobRole/company/companyType ฝังไว้ ทำให้ระบบ
   ออก session ใหม่ให้เองอัตโนมัติ) แล้ว sniff network request หา qsid/insid จริง
   จากนั้นประกอบเป็น URL แบบเดิมที่ scraper.py ใช้ได้ปกติ, เซฟไว้ใช้ต่อ
4. ถ้า discover() ก็ล้มเหลว -> raise ให้ main.py ไปแจ้ง Telegram/admin ต่อ

หมายเหตุ: เซฟ state ไว้ใน Supabase (ไม่ใช่ไฟล์ local) เพราะ GitHub Actions runner
เป็นเครื่องใหม่ทุกครั้งที่รัน ไฟล์ local จะหายหมดหลังจบ job
"""

import os
import re
from playwright.sync_api import sync_playwright

from supabase_client import get_client

CONFIG_KEY = "quikstrike_url"

# entry point ที่ "bootstrap" session ใหม่ได้เองโดยไม่ต้องมี qsid ที่ยังไม่หมดอายุอยู่ก่อน
# (userId/jobRole/company/companyType เป็นพารามิเตอร์สาธารณะที่ CME ใช้ระบุ user ประเภท trial/demo
# ไม่ใช่ credential ลับอะไร แต่ก็ไม่ควร hardcode ผิดที่ผิดทาง — ย้ายมาเป็นค่า default ที่ override ได้)
DISCOVER_ENTRY_URL_TEMPLATE = (
    "https://cmegroup-tools.quikstrike.net/User/QuikStrikeTools.aspx?"
    "viewitemid=IntegratedV2VExpectedRange"
    "&pid={pid}"
    "&userId={user_id}"
    "&jobRole={job_role}"
    "&company={company}"
    "&companyType={company_type}"
)

# URL แบบเต็มที่ scraper.py ใช้งานได้จริง (รูปแบบเดียวกับที่เคยตั้งเองใน .env.example)
FINAL_URL_TEMPLATE = (
    "https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx?"
    "pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange&insid={insid}&qsid={qsid}"
)

REFERER = "https://www.cmegroup.com/tools-information/quikstrike/vol2vol-expected-range.html"


class UrlManagerError(Exception):
    pass


class UrlManager:
    def __init__(self):
        self._client = get_client()  # public schema — app_config อยู่ตรงนี้

    # ---------- Supabase persistence ----------

    def get_saved_url(self) -> str | None:
        try:
            result = (
                self._client.table("app_config")
                .select("value")
                .eq("key", CONFIG_KEY)
                .execute()
            )
            if result.data:
                return result.data[0]["value"]
        except Exception as e:
            print(f"⚠️  อ่าน {CONFIG_KEY} จาก Supabase ไม่สำเร็จ: {e}")
        return None

    def save_url(self, url: str) -> None:
        try:
            self._client.table("app_config").upsert(
                {"key": CONFIG_KEY, "value": url}
            ).execute()
            print(f"✅ บันทึก QuikStrike URL ใหม่ลง Supabase (app_config) แล้ว")
        except Exception as e:
            print(f"⚠️  บันทึก {CONFIG_KEY} ไม่สำเร็จ: {e}")

    # ---------- validate ----------

    def validate(self, url: str) -> bool:
        """เปิด url จริงแล้วเช็คว่ามี Highcharts โหลดสำเร็จไหม (ไม่ error/session หมดอายุ)"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

                has_chart = page.evaluate(
                    "() => typeof Highcharts !== 'undefined' "
                    "&& Highcharts.charts && Highcharts.charts.some(c => c)"
                )
                page_text = (page.evaluate("() => document.body.innerText") or "").lower()
                browser.close()

            has_error_text = any(
                kw in page_text
                for kw in ("session expired", "session has expired", "not found", "an error occurred")
            )
            return bool(has_chart) and not has_error_text
        except Exception as e:
            print(f"⚠️  validate() เปิด URL ไม่สำเร็จ: {e}")
            return False

    # ---------- discover ----------

    def _try_extract_from_html(self, page) -> tuple[str | None, str | None]:
        """เช็คก่อนสุด: qsid/insid อาจฝังอยู่ใน HTML/JS ของหน้าตรงๆ (เร็วและชัวร์กว่า sniff
        network event ซึ่งมีปัญหาเรื่อง timing — อาจ capture ไม่ทันถ้า request ยิงเร็วเกินไป)"""
        try:
            html = page.content()
        except Exception:
            return None, None

        qsid = None
        insid = None

        # qsid มักเป็นรูปแบบ GUID (8-4-4-4-12 hex)
        m = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            html, re.I,
        )
        if m:
            qsid = m.group(0)

        m = re.search(r"\binsid['\"=: ]+(\d+)", html, re.I)
        if m:
            insid = m.group(1)

        return qsid, insid

    def _try_extract_from_window(self, page) -> tuple[str | None, str | None]:
        """เช็คลำดับ 2: ตัวแปรใน window object ที่ชื่อคล้าย qs/session/ins/quik/view"""
        try:
            keys = page.evaluate("""
                () => Object.keys(window).filter(k => /qs|session|ins|quik|view/i.test(k))
            """)
        except Exception:
            return None, None

        qsid = None
        insid = None
        for k in keys or []:
            try:
                value = page.evaluate(f"() => window['{k}']")
            except Exception:
                continue
            if not isinstance(value, str):
                continue
            if not qsid and re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value, re.I):
                qsid = value
            if not insid and re.match(r"^\d+$", value):
                insid = value

        return qsid, insid

    def _try_extract_from_network(
        self, page, context, entry_url: str, wait_ms: int
    ) -> tuple[str | None, str | None]:
        """fallback สุดท้าย: sniff network request หา qsid/insid จาก AjaxPages call
        (วิธีนี้ใช้ตอนที่ qsid/insid ถูกสร้างฝั่ง server แล้วส่งผ่าน request เท่านั้น
        ไม่เคยโผล่ใน HTML/window เลย — จากที่คุณเทสมา นี่คือ pattern ที่พบบ่อยสุดของ QuikStrike)"""
        urls: list[str] = []

        def capture(req):
            url = req.url
            if "QuikStrike" in url or "qsid" in url or "insid" in url or "AjaxPages" in url:
                urls.append(url)

        page.on("request", capture)
        page.goto(entry_url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(wait_ms)

        qsid = None
        insid = None
        for u in urls:
            m = re.search(r"qsid=([^&]+)", u)
            if m:
                qsid = m.group(1)
            m = re.search(r"insid=([^&]+)", u)
            if m:
                insid = m.group(1)

        if not qsid or not insid:
            print(f"⚠️  [discover/network] หา qsid/insid ไม่ครบ (qsid={qsid}, insid={insid}) "
                  f"— จับ request ได้ทั้งหมด {len(urls)} รายการ")

        return qsid, insid

    def discover(
        self,
        pid: str = "25",
        user_id: str = "UR000777286",
        job_role: str = "Trading/Investing",
        company: str = "IVR",
        company_type: str = "University/Education",
        wait_ms: int = 20000,
    ) -> str | None:
        """เปิด QuikStrike จาก entry point ที่ bootstrap session ใหม่ได้เอง
        ลองหา qsid/insid ตามลำดับ: HTML regex -> window vars -> network sniffing"""
        entry_url = DISCOVER_ENTRY_URL_TEMPLATE.format(
            pid=pid, user_id=user_id, job_role=job_role,
            company=company, company_type=company_type,
        )

        qsid = None
        insid = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(extra_http_headers={"Referer": REFERER})
                page = context.new_page()

                print("    [discover] เปิด QuikStrike bootstrap entry point...")
                page.goto(entry_url, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(5000)

                # ลำดับ 1: HTML regex (เร็วสุด ไม่มีปัญหาเรื่อง timing)
                qsid, insid = self._try_extract_from_html(page)
                if qsid and insid:
                    print(f"    [discover] เจอจาก HTML โดยตรง (qsid={qsid[:8]}..., insid={insid})")

                # ลำดับ 2: window object
                if not (qsid and insid):
                    w_qsid, w_insid = self._try_extract_from_window(page)
                    qsid = qsid or w_qsid
                    insid = insid or w_insid
                    if qsid and insid:
                        print(f"    [discover] เจอจาก window object (qsid={qsid[:8]}..., insid={insid})")

                # ลำดับ 3: network sniffing (ต้อง reload ใหม่เพื่อจับ request ตั้งแต่ต้น)
                if not (qsid and insid):
                    print("    [discover] ไม่เจอใน HTML/window — reload แล้ว sniff network request แทน")
                    n_qsid, n_insid = self._try_extract_from_network(page, context, entry_url, wait_ms)
                    qsid = qsid or n_qsid
                    insid = insid or n_insid

                browser.close()
        except Exception as e:
            print(f"⚠️  [discover] เปิดหน้าไม่สำเร็จ: {e}")
            return None

        if not qsid or not insid:
            print(f"⚠️  [discover] หา qsid/insid ไม่ครบทั้ง 3 วิธี (qsid={qsid}, insid={insid})")
            return None

        new_url = FINAL_URL_TEMPLATE.format(insid=insid, qsid=qsid)
        print(f"✅ [discover] เจอ qsid/insid ใหม่ -> {new_url}")
        return new_url

    # ---------- orchestrator (retry ladder) ----------

    def get_url(self) -> str:
        saved = self.get_saved_url()
        if saved and self.validate(saved):
            print("✅ ใช้ URL ที่เคยบันทึกไว้ใน Supabase (ยังใช้งานได้)")
            return saved

        env_url = os.environ.get("QUIKSTRIKE_URL")
        if env_url and env_url != saved and self.validate(env_url):
            print("✅ ใช้ URL จาก env/Secret (ใช้งานได้) — บันทึกทับของเก่าใน Supabase")
            self.save_url(env_url)
            return env_url

        print("⚠️  URL เดิมทั้งหมดใช้ไม่ได้แล้ว กำลัง discover URL ใหม่ด้วย Playwright...")
        new_url = self.discover()
        if new_url and self.validate(new_url):
            self.save_url(new_url)
            return new_url

        raise UrlManagerError(
            "หา QuikStrike URL ที่ใช้งานได้ไม่สำเร็จเลย (saved, env, discover ล้มเหลวหมด) "
            "— อาจต้องเช็คว่า CME เปลี่ยนโครงหน้า QuikStrike หรือ CME ล่มจริงๆ"
        )
