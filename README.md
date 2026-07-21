# OI-intraday

Pipeline ดึงข้อมูล Options Flow (Vol2Vol Expected Range) จาก CME QuikStrike
สำหรับ XAUUSD (Gold) → เก็บลง Supabase → วิเคราะห์ด้วย Claude API → ส่งต่อ QontWise

## สถาปัตยกรรม

```
scraper.py (Playwright)
    -> ดึงข้อมูลจาก Highcharts object ในหน้า QuikStrike โดยตรง

parser.py
    -> แปลง raw JSON เป็น schema ที่ใช้งานได้ (P/C ratio, delta levels ฯลฯ)

analyze.py
    -> ส่งข้อมูลที่ parse แล้วเข้า Claude API เพื่อสรุปเป็น sentiment/insight

supabase_client.py
    -> insert record ลง Supabase table `options_flow_snapshots`

main.py
    -> orchestrate ทั้ง 4 ขั้นตอนข้างบนเป็น pipeline เดียว
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # แล้วกรอกค่าจริง
python src/main.py
```

## Environment Variables

ดู `.env.example` — ต้องมี:
- `QUIKSTRIKE_URL` — URL หน้า Vol2Vol ที่จะดึง (session id เปลี่ยนได้ ต้อง refresh เป็นระยะ)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — จาก Supabase Dashboard → Settings → API
  **ห้าม commit ค่าเหล่านี้ลง git เด็ดขาด ใช้ GitHub Secrets สำหรับ CI**
- `GEMINI_API_KEY` — สำหรับขั้นตอนวิเคราะห์ (เอาได้ฟรีจาก https://aistudio.google.com/apikey)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — สำหรับส่งผลวิเคราะห์เข้า Telegram
  (หา `chat_id` ได้จากส่งข้อความหา bot แล้วเปิด `https://api.telegram.org/bot<token>/getUpdates`)

## ข้อควรระวัง (สำคัญ)

1. **Data license / ToS** — CME market data มีเงื่อนไขการใช้งาน ใช้เพื่อวิเคราะห์ส่วนตัวเท่านั้น ห้ามเผยแพร่ข้อมูลดิบต่อสาธารณะ
2. **Session (`qsid`) หมดอายุ** — URL ผูกกับ session id ที่อาจหมดอายุ ต้องมีแผน refresh URL เป็นระยะ (ยังไม่ auto-refresh ใน v1 นี้)
3. **โครงหน้าเปลี่ยน** — ถ้า CME เปลี่ยน UI, scraper อาจพังกะทันหัน — ดู `scraper.py` มันจะ raise error ชัดเจนถ้า `Highcharts.charts` ว่างเปล่า อย่า silent-fail
4. **ความถี่การรัน** — แนะนำ 2-4 ครั้ง/วัน ไม่ใช่ real-time เพื่อลดความเสี่ยงโดน rate-limit/บล็อก IP

## GitHub Actions (scheduled scraping)

ดู `.github/workflows/scrape.yml` — รันตาม cron schedule, ใช้ GitHub Secrets สำหรับ credentials ทั้งหมด
ปรับ schedule ได้ตามช่วง session ที่สนใจ (London open / NY open / EOD)

## Supabase Schema

ดู `supabase/migrations/001_init.sql` — table `options_flow_snapshots` มี RLS เปิดอยู่ (ไม่มี public policy)
เข้าถึงได้เฉพาะผ่าน service role key เท่านั้น
