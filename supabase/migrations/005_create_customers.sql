-- customers: รายชื่อคนที่จะได้รับรายงานทาง Telegram
-- เพิ่ม/ปิด access ลูกค้าใหม่ = insert/update แถวในตารางนี้ ไม่ต้องแตะ GitHub Secret หรือโค้ดอีก

create table if not exists customers (
    id bigint generated always as identity primary key,
    chat_id text not null unique,
    name text,
    active boolean not null default true,
    notes text,
    created_at timestamptz not null default now()
);

comment on table customers is 'รายชื่อ Telegram chat_id ที่จะได้รับรายงาน options flow — เพิ่ม/ปิดคนได้โดยไม่ต้องแก้โค้ดหรือ Secret';
comment on column customers.chat_id is 'Telegram chat id ของลูกค้า (ตัวเลข string เช่น 6366135709)';
comment on column customers.active is 'true = ยังส่งให้อยู่, false = ปิด access ชั่วคราวโดยไม่ต้องลบแถว';

-- ตัวอย่างการเพิ่มลูกค้า (แก้ chat_id/name ตามจริงแล้วรันเองใน Supabase SQL editor):
insert into customers (chat_id, name) values
    ('6366135709', 'Sompong Wong'),
    ('7809999023', 'Kong Kk'),
    ('6892594260', 'EX')
on conflict (chat_id) do nothing;
