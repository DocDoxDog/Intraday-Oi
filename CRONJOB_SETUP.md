# Cron-Job.org → Repository Dispatch Setup

**v2 (2026-08-15): ระบบ trigger เดียวของ CP Hunter — ไม่มี cron ในโค้ด workflow ใดๆ**

## หลักการ

GitHub Actions `schedule:` ถูกตัดออกทั้งหมด (ทั้งที่มีอยู่และที่ไม่มี) Cron-job.org ทำหน้าที่เป็น "นาฬิกากลาง" เดียว ยิง `repository_dispatch` เข้า repo ทุกครั้งตามตารางด้านล่าง

Secret อยู่ใน GitHub **ทั้งหมด** (ไม่ต้องใส่ secret อะไรบน cron-job.org):
- **PAT_DISPATCH**: Personal Access Token (classic) scope `repo` — set เป็น GitHub Secret ของ repo

## คำสั่ง curl ต่อ job

แทนที่ `<OWNER>`, `<REPO>` และ `<TOKEN>` ตามจริง — cron-job.org job ใช้ mode **Custom URL / cURL**

### 1. scrape-hourly (scrape.yml — 4 โลหะ × 4 views)
- Schedule: `0 * * * *` (ทุกชั่วโมง)
- ช่วงเวลา: เฉพาะ 07:00–22:00 ICT (ตั้ง "Active at" / schedule ช่วงเดียวบน cron-job.org)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"scrape-hourly"}'
```

### 2. news-weekday (news_bot run.yml — จ–ศ)
- Schedule: `0 * * * *` (ทุกชั่วโมง)
- Ch่วงเวลา: เฉพาะ 08:00–21:00 ICT, จันทร์–ศุกร์
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"news-weekday"}'
```

### 3. news-weekend (news_bot run-weekend.yml — เส–อา)
- Schedule: `30 19 * * 6,0` (19:30 ICT เสาร์/อาทิตย์)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"news-weekend"}'
```

### 4. price-15m (price_engine.yml — GOLD M5)
- Schedule: `2,17,32,47 * * * *` (:02 :17 :32 :47)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"price-collect","client_payload":{"interval":"15m"}}'
```

### 5. price-30m (price_engine.yml — SILVER/FX 30m)
- Schedule: `2,32 * * * *` (:02 :32)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"price-collect","client_payload":{"interval":"30m"}}'
```

### 6. price-live-gate (price_engine.yml — Phase 2 Live Gate)
- Schedule: กดมือเมื่อต้องการ (หรือตั้งเป็นรายวันจริง ๆ 08:00 ICT: `0 1 * * *`)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"price-live-gate","client_payload":{"interval":"live_gate"}}'
```

### 7. judge-hourly (cross-market-judge.yml — Cross-Market Final Judge)
- Schedule: `20 * * * 1-5` (ทุก :20 ICT จ–ศ — หลัง scrape-hourly 20 นาทีพอ scrape จบ)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"judge-hourly"}'
```

### 8. calendar-fetch (economic_calendar.yml — ใน repo ตัวจริงอาจยังไม่มีไฟล์นี้)
- Schedule: `0 1,13,14,15,16 * * *` (08:00 pull + refresh 20–23 ICT)
- Command:
```bash
curl -s -X POST "https://api.github.com/repos/<OWNER>/<REPO>/dispatches" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"event_type":"calendar-fetch"}'
```

## แผนโควตา cron-job.org (Free tier = 50 jobs/week)

| Job | calls/สัปดาห์ |
|---|---|
| scrape-hourly (15 ชม./วัน × 7) | 105 ❗เกิน |
| news-weekday (14 ชม. × 5) | 70 ❗เกิน |
| อื่น ๆ | ~40 |

**⚠ สำคัญ: รวมทั้งหมด ~215 calls/สัปดาห์ เกินโควตา free (50) มาก** — ทางเลือก:

1. **Upgrade cron-job.org** (Pro ~$6.99/เดือน → 1,000 jobs/week) — recommended ถ้าอยากได้ hourly จริงทุกตัว
2. **ลดช่วง scrape** ให้เหลือ 07:00–16:00 ICT เฉพาะวันจันทร์–ศุกร์ (~75 calls) + news ลดเป็นช่วงตลาดเปิด — ยังเกิน free นิดนึง
3. **ผสม:** ใช้ cron-job.org เฉพาะ scrape-hourly (เกินโควตา = upgrade) หรือปล่อย price/calendar ใช้ GitHub cron เดิม (ต่ำสุด 5 นาที — price ใช้ได้) และ cron-job.org เฉพาะตัวที่ไม่มี cron
4. **GitHub schedule ทั้งหมด** (กลับไปใช้ cron ในโค้ด): free, unlimited — แต่มี jitter 1–2 ชม. ช่วง peak และ workflow scrape/news เดิมไม่มี cron

> ข้อ 3 เป็นทางสายกลางที่พบบ่อย: cron-job.org เป็น fallback/dispatch layer ส่วน GitHub schedule เป็นนาฬิการอง — แต่ตามคำขอ "cron ในโค้ดไม่ต้อง ใช้ cron-job.org" ให้ใช้ cron-job.org เป็น primary และตัดสินใจแผนโควตาด้วยตนเองตาม budget

## การทดสอบด้วยมือ

- กด "Test now" บน cron-job.org → เห็นผลทันทีใน Actions tab
- หรือกดรันจาก GitHub UI (workflow_dispatch) โดย event type ที่ workflow นั้น ๆ รองรับ

## Dead-man switch (แนะนำ)

เพิ่ม heartbeat step ท้าย scrape.yml → ส่ง Telegram ถ้า job ล้มเหลว 2 รอบติด (อ้างอิงจาก design docs):

```yaml
      - name: Heartbeat on failure
        if: failure()
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=⚠️ scrape-hourly ล้มเหลว (run #${{ github.run_number }}) — ตรวจสอบ cron-job.org + QuikStrike session"
```
