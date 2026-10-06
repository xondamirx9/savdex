-- Telegram-бот: привязка по ИНН и рассылка новых объявлений и тендеров
-- по категориям компании (savdex/telegram_bot.py, savdex/telegram_feed.py).
--
-- telegram_bot_chats — разговор с ботом до привязки: на каком шаге чат
-- (ИНН → почта → код), какой ИНН ввели, кому ушёл код. link_user_id —
-- человек пришёл кнопкой из кабинета: ему ИНН нужен только для сверки,
-- кода нет. Строка живёт и после привязки — в ней счётчики ошибок.

create table telegram_bot_chats (
    chat_id varchar(32) primary key,
    state varchar(8) not null default 'inn' check (state in ('inn', 'email', 'code', 'done')),
    locale varchar(5) not null default 'ru',
    link_user_id bigint references users (id) on delete set null,
    tin varchar(20),
    user_id bigint references users (id) on delete set null,
    code_hash varchar(64),
    code_expires_at timestamp(0) without time zone,
    -- Неверные ИНН, почта и код подряд; на пороге — пауза до locked_until
    mistakes smallint not null default 0,
    locked_until timestamp(0) without time zone,
    -- Сколько писем с кодом ушло за текущий час (с codes_window_at)
    codes_sent smallint not null default 0,
    codes_window_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);

-- Что рассылка уже разобрала: объявление или тендер попадает сюда один
-- раз — и после отправки, и когда оно старое и не отправлялось.
create table telegram_feed_items (
    kind varchar(8) not null check (kind in ('listing', 'tender')),
    item_id bigint not null,
    processed_at timestamp(0) without time zone not null,
    primary key (kind, item_id)
);

-- Уже опубликованное до запуска рассылки — разобрано: иначе первый проход
-- разослал бы всю витрину. Черновики и объявления на проверке — нет:
-- их опубликуют после запуска, и это будет новость
insert into telegram_feed_items (kind, item_id, processed_at)
select 'listing', id, now() from listings
where status = 'active' or published_at is not null;

insert into telegram_feed_items (kind, item_id, processed_at)
select 'tender', id, now() from tenders
where status = 'published' or published_at is not null;

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on telegram_bot_chats to savdex_django;
        grant select, insert, update, delete on telegram_feed_items to savdex_django;
    end if;
end $$;
