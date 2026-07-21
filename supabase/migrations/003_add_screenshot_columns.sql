alter table options_flow_snapshots add column if not exists screenshot_url text;
alter table options_flow_snapshots add column if not exists screenshot_path text;
-- screenshot_url: signed URL ที่ใช้ตอน capture (หมดอายุใน 1 ชม. — เก็บไว้อ้างอิงเฉยๆ)
-- screenshot_path: path ถาวรใน bucket oi-screenshots — ใช้ regenerate signed url ใหม่ได้
-- ผ่าน supabase_client.get_signed_url(path) ตอนอยากดูรูปย้อนหลัง
