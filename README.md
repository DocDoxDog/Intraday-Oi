# OI-intraday

Pipeline ดึงข้อมูล Options Flow (Vol2Vol Expected Range) จาก CME QuikStrike สำหรับ Gold Futures แล้วเก็บลง Supabase, วิเคราะห์ และส่งต่อ Telegram/LINE

## กลไก scraping ปัจจุบัน

หน้า QuikStrike รุ่นปัจจุบันไม่ได้สร้าง Highcharts object สำหรับแท็บ Intraday แบบเดิมเสมอไป แต่ส่ง chart เป็น PNG ที่มี HTML image-map กำกับอยู่ ค่าใน tooltip ราย strike ถูกเก็บใน attribute `fields` ของ `<area>`. `src/scraper.py` จึงทำงานดังนี้:

1. เปิดหน้า QuikStrike ด้วย Playwright
2. สั่ง postback ที่แท็บ `MainContent_ucViewControl_IntegratedV2VExpectedRange_1_lbIntraday`
3. อ่าน `map area[fields]` โดยตรง แทนการ parse รูปภาพหรือ OCR
4. เก็บข้อมูลทุก strike, expected range, delta marker, DataObjectId, chart URL และ screenshot
5. `src/parser.py` แปลงค่า numeric และรักษาข้อมูลราย strike ไว้ใน `raw_series` พร้อมคีย์เดิมที่ pipeline ใช้อยู่

ถ้า CME เปลี่ยนกลับไปสร้าง Highcharts, scraper ยังมี legacy fallback สำหรับ Highcharts object เดิม

## ฟิลด์ที่ดึงได้จาก Intraday

ใน `raw_series.strike_rows` มีข้อมูลต่อ strike ได้แก่ strike, call/put/straddle premium, settle, change, implied volatility, call/put delta, gamma, vega, theta, call/put/total open interest และการเปลี่ยนแปลง, call/put/total volume และการเปลี่ยนแปลง, intraday volume แยก call/put/total รวมถึง class flags ที่หน้าเว็บใช้บอกทิศทางขึ้น/ลง

ใน `raw_series.expected_ranges` มีช่วง One, Two และ Three Standard Deviations พร้อม lower/upper, เปอร์เซ็นต์ความน่าจะเป็น และเปอร์เซ็นต์การเบี่ยงเบนจากราคาอนาคต ส่วน `raw_series.delta_markers` มีระดับ 5/15/25/35/45 delta ฝั่ง Call/Put ตามที่หน้าแสดง

`put_volume` และ `call_volume` ใน schema เดิมหมายถึง **Intraday Volume** ตามตัวชี้วัดของแท็บ Intraday ส่วน regular Volume, OI และยอดรวมทุกประเภทเก็บเพิ่มเติมไว้ใน `raw_series.totals` และใน `strike_rows`

## Expiration policy

ก่อน scrape ระบบจะเปิด expiration selector และเลือก Gold Options Friday series รหัส `OG<number><month><year>` ที่มี DTE เป็นบวกน้อยที่สุด โดยไม่เลือก Gold Futures daily series รหัส `G...`. ในสัปดาห์สุดท้ายของเดือน ระบบจะเลือก standard monthly options รหัส `OG<month><year>` ของเดือนปัจจุบันแทน weekly. ค่า `dte` ใช้ fractional DTE จาก expiration selector เช่น `3.27` แทนค่าในหัวกราฟที่อาจปัดลงเป็น `3 DTE`; รายละเอียด selection ถูกเก็บใน `raw_series.expiration_selection`

## Twelve Data Futures-to-CFD conversion

เมื่อมี `TWELVEDATA_API_KEY` ระบบจะดึงราคาปิด XAU/USD ล่าสุดจาก Twelve Data แล้วคำนวณ basis จาก snapshot เดียวกันดังนี้: `diff = Futures price - Spot price` และ `CFD level = Futures level - diff`. ค่า Futures จาก QuikStrike จะไม่ถูกเขียนทับ. ระบบเก็บ `spot_price`, `basis_diff`, `cfd_price`, `raw_series.cfd_strike_rows` และ `raw_series.cfd_expected_ranges` เพิ่มเติม เพื่อให้รายงานใช้ระดับ OI และ Expected Range ในหน่วย CFD ได้. ต้องเพิ่ม `TWELVEDATA_API_KEY` ใน GitHub Actions Secrets; หากไม่มี key ระบบจะใช้ระดับ Futures แบบเดิมและไม่ทำให้ pipeline ล้มเหลว

เมื่อมี key เดียวกัน ระบบยังดึง OHLC ของ `H4`, `H1`, `M15`, `M5` และ `M1` เพื่อคำนวณ EMA50/EMA200, trend, liquidity sweep, BOS, FVG และ Fibonacci ภายใน `technical_context`. ข้อมูลนี้ส่งให้ AI ใช้ยืนยันหรือหักล้าง Bias และคัดกรอง Entry/SL/TP/RR แต่ไม่แสดงเป็นหัวข้อ indicator ในรายงานปกติของผู้รับ

## LINE delivery

ระบบส่งรายงาน LINE สองทางในรอบเดียวกัน: Broadcast ไปยังผู้ติดตาม/ผู้ที่แชทกับ OA ตามสิทธิ์ของ LINE และ Push Message ซ้ำไปยัง `LINE_GROUP_ID` หากตั้งค่าไว้. Group ID ไม่ถูกใช้แทนรายชื่อผู้ติดตาม และไม่ต้องเก็บ user ID รายคนสำหรับ Broadcast. ใน GitHub Actions ให้ตั้ง `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_GROUP_ID` และ `TWELVEDATA_API_KEY` เป็น Secrets.

## User 8622081180 micro-scalp

ผู้รับ `8622081180` ใช้การ์ดสั้นแยกจากรายงานทั่วไป โดยเลือกแผนเดียว (`LONG`, `SHORT` หรือ `WAIT`) และแสดง Entry/Limit, SL ไม่เกิน 10 ดอลลาร์ และ TP1–TP4 ระยะสั้น 5/10/15/20 ดอลลาร์. OI, IV, Flow, CFD conversion และ technical context ยังใช้คัดกรองภายในเหมือนเดิม แต่ไม่แสดง indicator ยาวในข้อความ.

## การจัดการ duplicate strike

CME อาจสร้าง image-map area ซ้ำสำหรับแท่งเดียวกันบนกราฟ บาง snapshot พบ strike ซ้ำ 10 จุด แต่ payload เหมือนกันทุกฟิลด์ parser จึง deduplicate เฉพาะรายการที่ payload เหมือนกันแบบครบถ้วน หากอนาคต payload ต่างกัน parser จะเก็บไว้ทั้งคู่เพื่อไม่ทิ้งข้อมูล

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python src/main.py
```

## Environment Variables

ดู `.env.example` สำหรับ `QUIKSTRIKE_URL`, Supabase, Gemini, Telegram และ LINE credentials. ห้าม commit credentials ลง git; ใช้ GitHub Secrets ใน CI

## ข้อควรระวัง

CME market data มีเงื่อนไขการใช้งาน ควรใช้เพื่อวิเคราะห์ส่วนตัวและไม่เผยแพร่ข้อมูลดิบต่อสาธารณะ. `qsid` อาจหมดอายุและระบบ URL manager จะพยายามหา session ใหม่ตามลำดับที่กำหนดไว้. ความถี่การดึงควรจำกัดเพื่อลดความเสี่ยง rate-limit และควรตรวจสิทธิ์การเข้าถึง QuikStrike ให้ตรงกับแผนบริการ

## Supabase Schema

ตารางเดิม `options_flow_snapshots` ยังรองรับฟิลด์หลักและ `raw_series` แบบ JSONB. migration ที่มีอยู่เพิ่ม `dte`, screenshot columns และ customer configuration ตามลำดับ
