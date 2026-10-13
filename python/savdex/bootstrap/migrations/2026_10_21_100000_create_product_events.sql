-- События продукта, которые нельзя посчитать в браузере (ТЗ-03, шаг 3):
-- деньги, модерация, ответы, сроки тарифов. Пишет savdex/product_events.py.
--
-- Персональных данных нет: компания и пользователь — номерами, в props —
-- коды, суммы, номера счетов и объявлений. occurred_at — в UTC.
-- ga_sent_at — для payment_succeeded: когда покупка ушла в GA4 через
-- Measurement Protocol (отправляет задача расписания, а не платёжный
-- обработчик — медленный Google не задерживает ответ банку).

create table product_events (
    id bigserial primary key,
    occurred_at timestamp(0) without time zone not null default (now() at time zone 'utc'),
    event varchar(64) not null,
    company_id bigint,
    user_id bigint,
    plan varchar(32),
    locale varchar(8),
    props jsonb not null default '{}'::jsonb,
    ga_sent_at timestamp(0) without time zone
);

create index product_events_event_occurred_at_index on product_events (event, occurred_at);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update on product_events to savdex_django;
        grant usage on sequence product_events_id_seq to savdex_django;
    end if;
end $$;
