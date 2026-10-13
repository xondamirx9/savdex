-- Второй фактор входа в админку: код из приложения (TOTP, RFC 6238 —
-- Google Authenticator, Яндекс Ключ, 1Password и т. п.), savdex/twofactor.py.
--
-- secret — ключ приложения, зашифрованный ключом от APP_KEY (Fernet):
-- утёкшая выгрузка базы без APP_KEY кодов не даёт. confirmed_at — первый
-- верный код введён, с этого момента вход без кода не пускает; пусто —
-- подключение начато, но не закончено. last_step — номер 30-секундного
-- шага последнего принятого кода: тот же код второй раз не проходит.
-- Ведёт только Django.

create table admin_two_factor (
    user_id bigint primary key references users (id) on delete cascade,
    secret text not null,
    confirmed_at timestamp(0) without time zone,
    last_step bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on admin_two_factor to savdex_django;
    end if;
end $$;
