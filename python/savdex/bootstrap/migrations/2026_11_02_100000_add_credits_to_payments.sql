-- Счёт на пакет контактов хранит число кредитов.
--
-- Раньше при оплате кредиты брались из самого пакета (credit_packs.credits),
-- а не из счёта. От расхождения защищал запрет менять число кредитов у
-- пакета с неоплаченными счетами, но только со счетами «ждёт оплаты»:
-- отменённый (failed) счёт может позже стать «оплачен» (запоздалое
-- подтверждение кассы, отметка администратора) и начислить кредиты по
-- новому числу в пакете — не тому, что было в счёте.
--
-- payments.credits — сколько кредитов обещано в счёте, записывается при
-- выставлении; null — счёт не на пакет. Уже выставленным счетам на пакет
-- число берётся из пакета сейчас: с этой минуты оно и есть обещанное.

alter table payments add column credits integer;
alter table payments add constraint payments_credits_positive
    check (credits is null or credits > 0);

update payments p set credits = c.credits
from credit_packs c
where c.id = p.credit_pack_id and p.purpose = 'credits' and c.credits > 0;
