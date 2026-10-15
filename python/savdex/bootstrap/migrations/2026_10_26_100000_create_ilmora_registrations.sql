-- Регистрация в ILMORA через Savdex (savdex/ilmora): заявка с формы
-- /register/ilmora-register. Аккаунт Savdex не заводится — только заявка,
-- её видит раздел админки «ILMORA — регистрации» (право ilmora.view).
--
-- phone — +998 и 9 цифр. Физлицо — pinfl (14 цифр), юрлицо — tin (9 цифр):
-- заполнено ровно одно, по person_type. offer_accepted_at и offer_signed_at —
-- время обеих галочек оферты (юридическое подтверждение), offer_version —
-- какой текст оферты был тогда. Повторы по телефону и ИНН не запрещены:
-- админка их помечает.
create table ilmora_registrations (
    id bigserial primary key,
    created_at timestamp(0) without time zone not null default (now() at time zone 'utc'),
    person_type varchar(16) not null,
    phone varchar(16) not null,
    full_name varchar(150) not null,
    pinfl varchar(14),
    tin varchar(9),
    offer_accepted_at timestamp(0) without time zone not null,
    offer_signed_at timestamp(0) without time zone not null,
    offer_version varchar(32) not null,
    locale varchar(8),
    ip varchar(45),
    user_agent varchar(500),
    constraint ilmora_registrations_person_type_check
        check (person_type in ('individual', 'legal')),
    constraint ilmora_registrations_number_check check (
        (person_type = 'individual' and pinfl is not null and tin is null)
        or (person_type = 'legal' and tin is not null and pinfl is null)
    )
);

create index ilmora_registrations_created_at_index on ilmora_registrations (created_at);
create index ilmora_registrations_phone_index on ilmora_registrations (phone);

do $$ begin
    if exists (select from pg_roles where rolname = 'savdex_django') then
        grant select, insert on ilmora_registrations to savdex_django;
        grant usage on sequence ilmora_registrations_id_seq to savdex_django;
    end if;
end $$;
