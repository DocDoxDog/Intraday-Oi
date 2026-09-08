# Gold Options Intraday Signal Card

## Executive summary

การรัน `src/main.py` แบบเต็มใน sandbox รอบนี้ยังไม่สามารถทดสอบการส่ง Telegram หรือ LINE ได้ เพราะ environment ของ GitHub Actions ไม่ได้ถูกโหลดใน sandbox และหยุดตั้งแต่ `SUPABASE_URL` ไม่มีค่า. อย่างไรก็ตาม log ที่ผู้ใช้ส่งมาก่อนหน้านี้ยืนยันว่า pipeline เดิมส่ง Telegram และ LINE ได้สำเร็จเมื่อรันใน GitHub Actions

รูปแบบข้อความ XAU SIGNAL AI ที่แนบมาเหมาะกับการสื่อสารที่อ่านเร็ว แต่ระบบ Gold Options ของเราไม่ควรนำค่า Call/Put volume ไปแปลเป็น Long หรือ Short โดยอัตโนมัติ เพราะข้อมูลนี้ไม่ได้ระบุว่าธุรกรรมเป็นการเปิดหรือปิดสถานะ และไม่ได้ระบุว่าฝั่งใดเป็นผู้ซื้อหรือผู้ขาย. รูปแบบที่เหมาะสมกว่าคือ **Options Flow Signal Card** ซึ่งแยก “Bias จาก options flow” ออกจาก “Trade action” และอนุญาตให้แสดง `WAIT` เมื่อยังไม่มี price confirmation

## รูปแบบข้อความที่เสนอ

```text
┌────────────────────────────┐
│   GOLD OPTIONS SIGNAL      │
│                            │
│ GC / G2RU6                 │
│ Expiry: Friday             │
│ DTE: 2.45                  │
│                            │
│       ⚪ WAIT               │
│ Flow Bias: CALL-LEANING    │
│ Confidence: 68%            │
│ Score: 68/100              │
│                            │
│ Future      4441.9         │
│ ATM IV      20.12%         │
│ Call/Put IV  826 / 529     │
│ Call/Put OI  1960 / 1616   │
│                            │
│ 1 SD Range  4415.4–4468.4  │
│ 2 SD Range  4389.2–4495.1  │
│                            │
│ Key Call Wall  4450 / 4500 │
│ Key Put Wall   4400 / 4425 │
│                            │
│ Action: รอราคา confirm     │
│ Long trigger: hold > wall  │
│ Short trigger: lose support│
└────────────────────────────┘
```

การ์ดควรตามด้วยรายละเอียดสั้นสองส่วน. ส่วนแรกอธิบายเหตุผลของคะแนน. ส่วนที่สองให้แผนจัดการเมื่อราคาเลือกทางใดทางหนึ่ง

```text
เงื่อนไข                         คะแนน
Call Intraday มากกว่า Put       +15
Call OI มากกว่า Put             +10
ราคาอยู่เหนือจุดสมดุล            +15
Call wall อยู่เหนือราคา          +10
Put wall รองรับด้านล่าง          +10
อยู่ใน 1 SD range                +10
IV และ expected range สอดคล้อง   +10
History ยืนยันทิศทาง             +10
คุณภาพข้อมูล                     +10
เต็ม                             100

แผน:
- ยังไม่เปิดสถานะจนกว่าจะมี price confirmation
- Long เมื่อยืนเหนือ resistance พร้อม volume confirmation
- Short เมื่อหลุด support พร้อม volume confirmation
- Stop อยู่เลย invalidation wall
- Target แรกเป็น wall ถัดไป และ target สองเป็น expected-range boundary
```

## Scoring model

คะแนนควรเป็น **deterministic score** ที่คำนวณจากข้อมูลดิบก่อนส่งเข้า Gemini. Gemini ควรทำหน้าที่อธิบายเหตุผลและจัดรูปข้อความ ไม่ควรเป็นผู้สุ่มคะแนนเอง

| หมวด | คะแนนเต็ม | ข้อมูลที่ใช้ | หลักการ |
|---|---:|---|---|
| Intraday flow imbalance | 15 | `ivolumeCall`, `ivolumePut` | ให้คะแนนเมื่อความต่างมากกว่าค่า threshold ที่กำหนด และเรียกว่า `CALL-LEANING` หรือ `PUT-LEANING` เท่านั้น |
| Open-interest structure | 15 | `oiCall`, `oiPut`, `oiTotal` | ใช้ระบุ concentration และ wall ไม่ตีความเป็น bullish โดยลำพัง |
| Price location | 15 | Future, 1/2/3 SD range | ระบุว่าราคาอยู่กลาง range, ใกล้ upper boundary หรือใกล้ lower boundary |
| Wall position | 15 | Strike ที่มี OI/volume สูงสุด | แยก call wall ด้านบนและ put wall ด้านล่างตามราคาปัจจุบัน |
| IV regime | 10 | ATM IV, strike IV, expected-range IV | ใช้บอกว่าควรคาดหวังการแกว่งมากหรือน้อย ไม่ใช้ IV สูงเป็นสัญญาณ Long/Short โดยตรง |
| Delta and Greeks | 10 | Delta markers, gamma, vega, theta | ใช้ประกอบความไวของราคาและโซน hedging เมื่อค่าพร้อมใช้งาน |
| History confirmation | 10 | snapshot ก่อนหน้าและ today summary | เพิ่มคะแนนเฉพาะเมื่อราคาและ flow เคลื่อนไปในทิศเดียวกันหลาย snapshot |
| Data quality | 10 | จำนวน strike, integrity checks, DTE source | ลดคะแนนหรือบังคับ `WAIT` เมื่อข้อมูลไม่ครบ, DTE เป็น 0 โดยไม่ใช่ policy, หรือ totals ไม่สมดุล |
| **รวม** | **100** |  |  |

## Signal state

ระบบควรใช้ state ที่ชัดเจนสี่ระดับเพื่อไม่ให้ข้อความดูมั่นใจเกินข้อมูล

| State | เงื่อนไขขั้นต่ำ | ความหมาย |
|---|---|---|
| `WAIT` | score ต่ำกว่า 70 หรือไม่มี price confirmation | มี flow แต่ยังไม่มีจุดเข้าเทรดที่ปลอดภัย |
| `LONG SETUP` | score อย่างน้อย 70, flow สนับสนุน, ราคา reclaim resistance | เป็น setup ไม่ใช่คำสั่งซื้อทันที |
| `SHORT SETUP` | score อย่างน้อย 70, flow สนับสนุน, ราคาหลุด support | เป็น setup ไม่ใช่คำสั่งขายทันที |
| `NO TRADE` | data quality ต่ำหรือ range/expiry ไม่ถูกต้อง | งดส่ง entry, stop และ target ที่ดูเหมือนแม่นยำ |

คำว่า `CALL-LEANING` หรือ `PUT-LEANING` ควรใช้แทน `BULLISH` หรือ `BEARISH` เมื่อหลักฐานมีเพียง options flow. ระบบจะแสดง `LONG SETUP` หรือ `SHORT SETUP` ได้เมื่อมี price confirmation จาก snapshot ปัจจุบันและประวัติ

## การสร้าง Entry, Stop และ Target

ระบบไม่มี EMA, BOS, FVG หรือ Liquidity Sweep ใน QuikStrike payload ปัจจุบัน. จึงไม่ควรพิมพ์เงื่อนไขเหล่านี้ลงการ์ดจนกว่าจะเพิ่มแหล่งข้อมูลราคาและ technical indicators โดยเฉพาะ

สำหรับ options-only version ให้ใช้กฎดังนี้

| รายการ | วิธีคำนวณ |
|---|---|
| Long trigger | ราคายืนเหนือ call wall หรือ upper local resistance และ flow ไม่พลิกเป็น put-heavy |
| Short trigger | ราคาหลุด put wall หรือ lower local support และ flow ไม่พลิกเป็น call-heavy |
| Initial stop | อีกด้านของ wall ที่ใช้เป็น invalidation โดยบวก buffer ตาม tick size |
| Target 1 | wall ถัดไปในทิศทางเดียวกัน |
| Target 2 | ขอบ 1 SD หรือ 2 SD ตาม volatility regime |
| Wait trigger | ราคาอยู่กลาง range, wall ไม่ชัด, หรือ Call/Put ต่างกันน้อย |

ทุกค่า Entry, Stop และ Target ต้องติดป้ายว่าเป็น `ระดับเงื่อนไข` ไม่ใช่ราคาที่รับประกันว่าจะเกิดขึ้น. หากราคายังไม่ trigger ให้แสดง `Entry: รอ confirm` แทนการสร้างตัวเลขขึ้นมาเอง

## ข้อมูลที่ต้องเพิ่มใน parsed output

โครงสร้างปัจจุบันมีข้อมูลพอสำหรับการ์ดรุ่นแรก. ควรเพิ่มคีย์สรุปที่คำนวณแบบ deterministic เพื่อให้ formatter และ Gemini ใช้ชุดข้อมูลเดียวกัน

```json
{
  "signal": {
    "state": "WAIT",
    "flow_bias": "CALL-LEANING",
    "score": 68,
    "confidence": 68,
    "reasons": [],
    "entry_trigger": null,
    "stop_trigger": null,
    "targets": []
  },
  "expiration_selection": {
    "selected": "G2RU6",
    "policy": "next_friday_weekly",
    "dte_hint": 2.45
  }
}
```

คีย์ `expiration_selection` ที่เพิ่มแล้วช่วยยืนยันว่า snapshot ใช้ Friday expiry จริง และช่วยป้องกันการกลับไปใช้ 0DTE โดยไม่ตั้งใจ

## การส่ง Telegram และ LINE

Telegram ควรส่งสามข้อความตามลำดับเดิม แต่เปลี่ยนเนื้อหาให้มีการ์ดก่อนรายงานละเอียด

1. ส่ง screenshot หากอัปโหลดสำเร็จ
2. ส่ง Signal Card แบบสั้นเพื่ออ่านเร็ว
3. ส่งรายงาน Options Flow และ Scenario แบบละเอียด

LINE ควรใช้โครงเดียวกัน แต่ตัด HTML ออกและคุมความยาวตามข้อจำกัดของ LINE. หากไม่มี screenshot ให้ส่งการ์ดต่อได้ เพราะ screenshot เป็นส่วนเสริม ไม่ใช่ dependency ของการวิเคราะห์

ตัวอย่างข้อความสั้นที่เหมาะกับระบบปัจจุบันคือ:

```text
GOLD OPTIONS SIGNAL
Expiry: G2RU6 | Friday | DTE 2.45
State: WAIT
Flow Bias: CALL-LEANING
Score: 68/100 | Confidence: 68%
Future: 4441.9 | ATM IV: 20.12%
Intraday Call/Put: 826/529
OI Call/Put: 1960/1616
1 SD: 4415.4–4468.4
2 SD: 4389.2–4495.1
Action: รอราคา confirm เหนือ call wall หรือหลุด put wall
```

## ข้อเสนอการพัฒนาตามลำดับ

ระยะแรกควรเพิ่ม deterministic scoring, signal card และ expiration metadata โดยยังคงรายงาน Gemini เดิมไว้. ระยะที่สองควรเพิ่ม price-history confirmation และคำนวณ wall/trigger แบบรวม duplicate strike. ระยะที่สามจึงค่อยเพิ่ม EMA, BOS, FVG และ liquidity sweep จาก data source ราคาแยกต่างหาก

การทดสอบ end-to-end ต้องรันใน GitHub Actions ซึ่งมี secrets ครบ. การรันใน sandbox จะหยุดที่ `SUPABASE_URL` หากไม่ได้โหลด environment เดียวกับ Actions และไม่ควรนำไปสรุปว่า Telegram หรือ LINE ใช้งานไม่ได้

## References

[1]: https://cmegroup-tools.quikstrike.net/User/QuikStrikeView.aspx?pid=40&pf=6&viewitemid=IntegratedV2VExpectedRange&insid=243453528&qsid=8864de90-aa5c-458d-a04c-f5651b03cf7c "QuikStrike Vol2Vol Expected Range page"
