# CHANGELOG

## v2 — 2026-08-15 (cron-job.org dispatch-only)

### เปลี่ยนแปลงหลัก

ระบบ trigger ทั้งระบบถูก migrate ไปใช้ **cron-job.org ยิง `repository_dispatch`** เป็นหน่วยงานเดียว ตัด `schedule: cron` ออกจาก workflow ทุกไฟล์ตามคำขอ

| ไฟล์ | เดิม | v2 |
|---|---|---|
| `intraday_oi/.github/workflows/scrape.yml` | workflow_dispatch + repo_dispatch `run-analysis` (ไม่เข้ากับ cron ใด) | repo_dispatch `scrape-hourly` + workflow_dispatch |
| `news_bot/.github/workflows/run.yml` | workflow_dispatch + repo_dispatch `run-analysis` | repo_dispatch `news-weekday` + workflow_dispatch |
| `news_bot/.github/workflows/run-weekend.yml` | cron `30 12 * * 6,0` | repo_dispatch `news-weekend` + workflow_dispatch |
| `.github/workflows/price_engine.yml` | cron `2,17,32,47` / `2,32` + inputs | repo_dispatch `price-collect` / `price-live-gate` (interval ผ่าน client_payload) + inputs |
| `.github/workflows/economic_calendar.yml` | cron 08:00–23:00 ICT | repo_dispatch `calendar-fetch` + workflow_dispatch |
| `intraday_oi/.github/workflows/support_action.yml` | workflow_dispatch เท่านั้น (เครื่องมือ manual) | ไม่เปลี่ยน |

### ไฟล์ใหม่

- `CRONJOB_SETUP.md` — คำสั่ง curl สำหรับ job ทั้ง 7 บน cron-job.org, ตาราง schedule (ICT), แผนโควตา free tier, และ dead-man switch heartbeat step

### การรัน jobs ที่ cron-job.org (สรุป)

| Job | Schedule (ICT) | Event |
|---|---|---|
| scrape-hourly | ทุกชม. 07:00–22:00 | `scrape-hourly` |
| news-weekday | ทุกชม. 08:00–21:00 จ–ศ | `news-weekday` |
| news-weekend | 19:30 เส–อา | `news-weekend` |
| price-15m | :02 :17 :32 :47 | `price-collect` + `{"interval":"15m"}` |
| price-30m | :02 :32 | `price-collect` + `{"interval":"30m"}` |
| price-live-gate | กดมือ/รายวัน | `price-live-gate` + `{"interval":"live_gate"}` |
| calendar-fetch | 08:00 pull + 20:00–23:00 refresh | `calendar-fetch` |

### ข้อควรทราบ

1. **โควตา cron-job.org free tier = 50 jobs/สัปดาห์** — total ~215 calls/สัปดาห์ เกิน; เลือกวิธี: upgrade Pro (~$6.99/เดือน = 1,000 jobs/week), ลดช่วงเวลา, หรือผสม GitHub schedule สำหรับ price/calendar (รายละเอียดใน CRONJOB_SETUP.md)
2. **PAT_DISPATCH**: สร้าง PAT (scope `repo`) → set เป็น GitHub Secret ก่อนสร้าง job ที่ cron-job.org
3. **ทดสอบมือ**: กดรันจาก Actions tab ได้ปกติผ่าน workflow_dispatch ทุก workflow
4. การ validate: ทุกไฟล์ yaml  parse ผ่าน, ไม่มี `schedule:`/`cron:` เหลือใน workflow ใด ๆ
