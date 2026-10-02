-- Этапы воронок продаж: лиды и сделки (доски в админке, savdex/crm/board.py).
--
-- Этап — колонка доски. Код этапа лежит в crm_leads.status / crm_deals.stage,
-- как и раньше: старые коды остаются системными этапами, новые этапы
-- администратор заводит сам (код «s<номер>»). Системные этапы не удаляются:
-- «new» — вход (с него начинает лид с сайта), «converted»/«won» и «lost» —
-- закрытые колонки, на них завязаны отчёты, «В сделку» и обязательная
-- причина отказа.
--
-- fields — поля окна при переводе на этап, их выбирает администратор:
-- {"owner": "required", "comment": "optional", ...} (каталог — savdex/crm/stages.py).
-- limit_days — сколько дней на этапе нормально; дольше — карточка красная.

create table crm_stages (
    id bigserial primary key,
    pipeline varchar(10) not null check (pipeline in ('leads', 'deals')),
    code varchar(20) not null,
    name varchar(80) not null,
    kind varchar(10) not null default 'open' check (kind in ('open', 'won', 'lost')),
    position integer not null default 0,
    limit_days integer check (limit_days is null or limit_days > 0),
    fields jsonb not null default '{}'::jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    unique (pipeline, code)
);

insert into crm_stages (pipeline, code, name, kind, position, limit_days, fields, created_at, updated_at) values
    ('leads', 'new', 'Новый', 'open', 1, 1, '{}', now(), now()),
    ('leads', 'working', 'В работе', 'open', 2, 7, '{"owner": "required", "comment": "optional"}', now(), now()),
    ('leads', 'qualified', 'Квалифицирован', 'open', 3, 7, '{"comment": "optional", "task": "optional"}', now(), now()),
    ('leads', 'converted', 'Стал сделкой', 'won', 4, null, '{}', now(), now()),
    ('leads', 'lost', 'Отказ', 'lost', 5, null, '{"lost_reason": "required"}', now(), now()),
    ('deals', 'new', 'Новая', 'open', 1, 3, '{}', now(), now()),
    ('deals', 'negotiation', 'Переговоры', 'open', 2, 14, '{"comment": "optional", "task": "optional"}', now(), now()),
    ('deals', 'proposal', 'Предложение отправлено', 'open', 3, 14, '{"amount": "required", "expected_close_at": "optional"}', now(), now()),
    ('deals', 'won', 'Выиграна', 'won', 4, null, '{"amount": "required"}', now(), now()),
    ('deals', 'lost', 'Проиграна', 'lost', 5, null, '{"lost_reason": "required"}', now(), now());

-- Когда карточка пришла на этап: «дней на этапе» и недельные закрытые колонки
alter table crm_leads add column stage_changed_at timestamp(0) without time zone;
alter table crm_deals add column stage_changed_at timestamp(0) without time zone;
update crm_leads set stage_changed_at = coalesce(updated_at, created_at);
update crm_deals set stage_changed_at = coalesce(closed_at, updated_at, created_at);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert, update, delete on crm_stages to savdex_django;
        grant usage on sequence crm_stages_id_seq to savdex_django;
    end if;
end $$;
