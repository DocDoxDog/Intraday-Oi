alter table options_flow_snapshots add column if not exists dte numeric;
-- DTE (Days to Expiration) ของ contract ที่ scrape มา
-- สำคัญเพราะ Gamma Exposure ที่ dealer ต้อง hedge เข้มข้นขึ้นแบบไม่เป็นเชิงเส้นเมื่อใกล้ expiration
-- (0DTE effect) — วอลุ่ม Put/Call เท่ากันแต่ DTE ต่างกัน ผลต่อราคาไม่เท่ากัน
