-- Старые адреса страниц (ТЗ-02 §4) — 301 на новые.
--
-- Китайская компания получила адрес /company/company (иероглифов в адресе
-- не было), её объявления — /listing/-861 … /listing/-864. Теперь адрес —
-- латиницей (пиньинь), а у объявления без латиницы — один номер. Чтобы
-- старые ссылки не сломались, прежний адрес остаётся здесь: страница по
-- нему отвечает 301 на текущий адрес записи target_id.
--
-- entity: company или listing. Адреса переписывает manage.py reslug при
-- каждом деплое (только те, что ещё плохие, — savdex/reslug.py).

create table slug_redirects (
    id bigserial primary key,
    entity varchar(16) not null check (entity in ('company', 'listing')),
    old_slug varchar(255) not null,
    target_id bigint not null,
    created_at timestamp(0) without time zone,
    unique (entity, old_slug)
);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on slug_redirects to savdex_django;
        grant usage on sequence slug_redirects_id_seq to savdex_django;
    end if;
end $$;
