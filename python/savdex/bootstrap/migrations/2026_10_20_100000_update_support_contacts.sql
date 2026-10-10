-- Контакты поддержки (ТЗ-01, п.1): прежний телефон и ссылка t.me/savdex —
-- уже не площадки (за ссылкой — чужой аккаунт). Меняется только старое
-- значение: если в админке успели вписать что-то своё, оно остаётся.
--
-- Часы поддержки (support_hours) сайт больше не показывает — они в
-- переводах contacts.hours_value на пяти языках, — поэтому старое
-- «Пн–Пт, 9:00–18:00 (Ташкент)» очищается, чтобы не вводить в
-- заблуждение в админке.
--
-- value — json: строка лежит как "…", текст из неё — value #>> '{}'.

update settings
set value = to_json('+998 77 188 48 80'::text), updated_at = now()
where key = 'support_phone'
  and regexp_replace(coalesce(value #>> '{}', ''), '\D', '', 'g') = '998914602027';

update settings
set value = to_json('https://t.me/savdex_admin'::text), updated_at = now()
where key = 'telegram'
  and lower(rtrim(trim(coalesce(value #>> '{}', '')), '/')) in
      ('https://t.me/savdex', 'http://t.me/savdex', 't.me/savdex', '@savdex');

update settings
set value = to_json(''::text),
    description = 'На сайте не показывается: часы поддержки на пяти языках — в переводах (contacts.hours_value)',
    updated_at = now()
where key = 'support_hours';
