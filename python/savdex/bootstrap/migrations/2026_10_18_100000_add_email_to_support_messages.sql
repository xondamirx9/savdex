-- Обращения по почте (savdex/support/mail.py): письмо на ящик поддержки
-- становится обращением, ответ поддержки уходит клиенту письмом.
--
-- email_message_id — Message-ID письма: у входящего — чтобы одно письмо не
-- завело два обращения, у ответа — чтобы ответ клиента на него нашёл своё
-- обращение. emailed_at — когда ответ ушёл клиенту, email_error — почему не
-- ушёл (видно в переписке). attachments — вложения письма (столбец был).
alter table support_messages add column email_message_id varchar(255);
alter table support_messages add column emailed_at timestamp(0) without time zone;
alter table support_messages add column email_error varchar(255);

create index support_messages_email_message_id_index
    on support_messages (email_message_id) where email_message_id is not null;

-- Отметка «ушло клиенту на почту» правит уже записанное сообщение: роли
-- Django раньше хватало вставки
do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant update on support_messages to savdex_django;
    end if;
end $$;
