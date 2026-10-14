-- Спам в поддержке (savdex/support/spam.py): «Спам» в обращении убирает его
-- в корзину и заносит отправителя в спам-фильтр — его письма больше не
-- становятся обращениями (savdex/support/mail.py). «Вернуть» в спам-фильтре
-- снимает блокировку и возвращает убранные обращения.
--
-- email — в нижнем регистре, один раз. support_tickets.spam_at — когда
-- обращение убрано как спам (deleted_at ставится то же): по нему «Вернуть»
-- находит, что восстановить, и не трогает удалённое по другим причинам.
create table support_blocked_senders (
    id bigserial primary key,
    email varchar(160) not null,
    blocked_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);

create unique index support_blocked_senders_email_unique on support_blocked_senders (email);

alter table support_tickets add column spam_at timestamp(0) without time zone;

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, delete on support_blocked_senders to savdex_django;
        grant usage on sequence support_blocked_senders_id_seq to savdex_django;
    end if;
end $$;
