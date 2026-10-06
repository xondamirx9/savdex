-- Потенциальные клиенты — база отдела продаж для рассылок (раздел CRM
-- «Потенциальные клиенты», savdex/crm/prospects.py).
--
-- Не компании площадки: это те, кто на SavdEx ещё не пришёл. Заливаются
-- файлом или заводятся вручную; данные бывают неполными — у физлица и
-- фрилансера нет ИНН, у кого-то только телефон, — поэтому обязательных
-- полей нет (одно из названия, имени, телефона, почты или ИНН проверяет
-- раздел). company_id — та же компания, если она уже зарегистрирована на
-- площадке (сверка по ИНН, почте, телефону).
--
-- mailings_count — счётчик рассылок: сколько писем и отмеченных вручную
-- касаний (Telegram, звонок…) получила запись. «В лиды» — lead_id и
-- converted_at: строка остаётся в базе с отметкой. unsubscribed_at —
-- отписался по ссылке в письме или попросил не писать: письма ему больше
-- не уходят.

create table crm_prospects (
    id bigserial primary key,
    kind varchar(20) check (kind in ('company', 'person', 'freelancer')),
    name varchar(190),
    tin varchar(20),
    contact_person varchar(160),
    phone varchar(100),
    email varchar(190),
    city varchar(120),
    industry varchar(190),
    website varchar(255),
    source varchar(120),
    note text,
    company_id bigint references companies (id) on delete set null,
    mailings_count integer not null default 0,
    last_mailed_at timestamp(0) without time zone,
    lead_id bigint references crm_leads (id) on delete set null,
    converted_at timestamp(0) without time zone,
    unsubscribed_at timestamp(0) without time zone,
    created_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);

create index crm_prospects_tin_index on crm_prospects (tin) where deleted_at is null;
create index crm_prospects_email_index on crm_prospects (lower(email)) where deleted_at is null;

-- Рассылка: письмо с площадки (email) или касание, отмеченное вручную
-- (mail — письмо со своей почты, telegram, whatsapp, call, sms, other). Письма уходят фоном
-- (manage.py notify), по строке получателя — queued → sent / failed /
-- skipped; total/sent/failed — итоги, finished_at — когда очередь пуста.
create table crm_prospect_mailings (
    id bigserial primary key,
    channel varchar(20) not null
        check (channel in ('email', 'mail', 'telegram', 'whatsapp', 'call', 'sms', 'other')),
    subject varchar(190),
    body text,
    reply_to varchar(190),
    note varchar(255),
    sent_by bigint,
    total integer not null default 0,
    sent integer not null default 0,
    failed integer not null default 0,
    finished_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);

create table crm_prospect_mailing_recipients (
    id bigserial primary key,
    mailing_id bigint not null references crm_prospect_mailings (id) on delete cascade,
    prospect_id bigint not null references crm_prospects (id) on delete cascade,
    email varchar(190),
    status varchar(10) not null default 'queued'
        check (status in ('queued', 'sending', 'sent', 'failed', 'skipped')),
    error varchar(255),
    sent_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    unique (mailing_id, prospect_id)
);

create index crm_prospect_mailing_recipients_queue_index
    on crm_prospect_mailing_recipients (id) where status in ('queued', 'sending');
create index crm_prospect_mailing_recipients_prospect_index
    on crm_prospect_mailing_recipients (prospect_id);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on
            crm_prospects, crm_prospect_mailings, crm_prospect_mailing_recipients
            to savdex_django;
        grant usage on sequence
            crm_prospects_id_seq, crm_prospect_mailings_id_seq,
            crm_prospect_mailing_recipients_id_seq
            to savdex_django;
    end if;
end $$;
