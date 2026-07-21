-- Bucket ตั้งเป็น private เพราะ CME market data ต้องใช้ส่วนตัวเท่านั้น (ดู README)
-- เข้าถึงรูปได้ผ่าน signed URL อายุสั้นเท่านั้น ไม่ใช่ public URL ตรงๆ
insert into storage.buckets (id, name, public)
values ('oi-screenshots', 'oi-screenshots', false)
on conflict (id) do nothing;
