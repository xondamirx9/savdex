-- Срок жизни тендера и чем он закончился (savdex/web/tender_actions.py,
-- savdex/tender_expiry.py).
--
-- source — откуда тендер: 'cabinet' — компания завела сама в «Мои
-- тендеры» (живёт 120 дней, продлевается, истекает сам), 'admin' —
-- администратор завёл в админке или загрузил из Excel (живёт по своему
-- сроку «Приём заявок до» из источника).
--
-- status: draft, published, archived (завершён владельцем или снят) и
-- expired — срок кабинетного тендера прошёл, а его не продлили.
--
-- outcome — чем закончился, отмечает владелец кнопкой «Завершить»:
-- contract — договорились (с какой компанией — outcome_party, сумма —
-- outcome_amount, пока не спрашивается), no_deal — «Сделка не
-- состоялась»; cancelled — запас на будущее. Пусто — ещё не завершён.
--
-- expiry_warned_at — предупреждение «через 3 дня истекает» ушло для
-- текущего срока; продление его сбрасывает.

alter table tenders
    add column source varchar(16) not null default 'admin',
    add column outcome varchar(16) check (outcome in ('contract', 'no_deal', 'cancelled')),
    add column outcome_party varchar(255),
    add column outcome_amount numeric(16, 2),
    add column finished_at timestamp(0) without time zone,
    add column expiry_warned_at timestamp(0) without time zone,
    add column extended_at timestamp(0) without time zone;

-- Кабинетные тендеры появились 6 октября 2026: раньше тендеры заводил
-- только администратор (в том числе со своей учётки — у них author_id)
update tenders t set source = 'cabinet'
where t.created_at >= '2026-10-06'
  and exists (select 1 from users u where u.id = t.author_id and not u.is_admin);

-- Кабинетный тендер без срока — 120 дней с публикации
update tenders set deadline_at = coalesce(published_at, created_at) + interval '120 days'
where source = 'cabinet' and deadline_at is null;

create index tenders_expiry_index on tenders (deadline_at) where source = 'cabinet' and status = 'published';
