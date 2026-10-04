-- Письма и Telegram по уведомлениям (savdex/deliveries.py): когда
-- уведомление прошло через рассылку — отправлено или пропущено по
-- настройкам. Прежние уведомления помечены сразу: иначе первый проход
-- разослал бы письма за всю историю.
alter table user_notifications add column delivered_at timestamp(0) without time zone;

update user_notifications set delivered_at = coalesce(created_at, now());

create index user_notifications_undelivered_index
    on user_notifications (id) where delivered_at is null;
