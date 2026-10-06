-- Визитки компании для QR-кода (кабинет → «Визитки»).
--
-- Визитка двух видов: фото настоящей визитки (kind = 'photo', image_path —
-- обрезанный в редакторе снимок) или собранная площадкой из полей
-- (kind = 'generated': название компании, Ф.И.О., почта, телефон).
-- token — случайный код в адресе /card/<token>, его кодирует QR: по номеру
-- визитки перебором не найти, в каталог и поиск страница не попадает.
-- Визиток у компании может быть несколько — например, на каждого сотрудника.

create table company_cards (
    id bigserial primary key,
    company_id bigint not null references companies (id) on delete cascade,
    user_id bigint references users (id) on delete set null,
    token varchar(32) not null unique,
    kind varchar(16) not null check (kind in ('photo', 'generated')),
    image_path varchar(255),
    company_name varchar(190),
    full_name varchar(190),
    email varchar(190),
    phone varchar(40),
    views_count integer not null default 0,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);

create index company_cards_company_id_index on company_cards (company_id);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on company_cards to savdex_django;
        grant usage on sequence company_cards_id_seq to savdex_django;
    end if;
end $$;
