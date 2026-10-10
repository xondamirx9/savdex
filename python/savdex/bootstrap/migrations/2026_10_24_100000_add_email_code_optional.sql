-- Регистрация без кода из письма — для отдельных стран.
--
-- Китайские почтовики (qq.com, 163.com) режут письма из-за рубежа, и
-- китайские клиенты не могли пройти регистрацию: код не приходил. Теперь
-- для стран с галочкой «Регистрация без кода» (справочник стран в админке)
-- на шаге кода есть «Продолжить без подтверждения»:
--
-- countries.email_code_optional — страна, где код можно пропустить;
-- users.email_code_skipped — человек пропустил код: сайт пускает его во
--   всё, как подтверждённого, пока он не подтвердит почту кодом;
-- companies.email_unconfirmed — над компанией, её объявлениями и
--   тендерами надпись «Не подтверждено»; снимает только подтверждение
--   почты владельцем.

alter table countries add column email_code_optional boolean not null default false;
alter table users add column email_code_skipped boolean not null default false;
alter table companies add column email_unconfirmed boolean not null default false;

update countries set email_code_optional = true where code = 'cn';
