"""
Демо-наполнение тестового сервера: придуманные компании, их владельцы,
объявления и отзывы (manage.py demo).

Тестовый сервер больше не берёт копию боевой базы: на нём только эти
данные, и письма с него уходят по-настоящему. Поэтому:

- на боевом (APP_ENV=production) команда отказывается работать;
- почты владельцев — в зоне .test (demo.savdex.test): писем туда не
  бывает, и сайт их не шлёт (savdex/web/mail.py — undeliverable);
- пароли владельцев случайные и нигде не записаны: под демо-учётками
  не входят, их смотрят на витрине и в админке;
- повторный запуск ничего не дублирует: демо-компании помечены
  (companies.source_note), и при них команда ничего не заводит.

Названия, ИНН, телефоны и люди придуманы; совпадение с настоящими —
случайность.
"""

from __future__ import annotations

import os
import random
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from django.db import connection, transaction

from savdex.tenders.slug import numbered_slug, slugify
from savdex.web.search_text import index

#: Метка демо-компании (companies.source_note)
MARK = "Демо-данные тестового сервера (manage.py demo)"

#: Почты владельцев: зона .test — писем туда не бывает
EMAIL_DOMAIN = "demo.savdex.test"


class DemoRefusedError(RuntimeError):
    """Демо-данные не для этой базы."""


# ── Что продают: подкатегория → (название, описание, единица, цена в сумах)

CATALOG: dict[str, list[tuple[str, str, str, int]]] = {
    "cement-beton": [
        (
            "Цемент М400 Д20 в мешках по 50 кг",
            "Портландцемент с минеральными добавками. Сертификат, паспорт качества на каждую партию. Отгрузка со склада в Ташкенте.",
            "мешок",
            52_000,
        ),
        (
            "Цемент М500 навалом",
            "Цемент без добавок для ответственных конструкций. Доставка цементовозом от 25 тонн.",
            "т",
            980_000,
        ),
        (
            "Бетон товарный B25 (М350)",
            "Бетон с завода, подвижность П3–П4. Доставка миксером, подача бетононасосом под заказ.",
            "м³",
            890_000,
        ),
    ],
    "kirpich-blok": [
        (
            "Кирпич керамический полнотелый М150",
            "Обожжённый красный кирпич 250×120×65. Морозостойкость F50. Отгрузка на поддонах по 300 штук.",
            "шт",
            1_350,
        ),
        (
            "Газоблок D500 600×300×200",
            "Автоклавный газобетон, точная геометрия под клей. Поддон 1,8 м³.",
            "м³",
            720_000,
        ),
        (
            "Пеноблок стеновой 600×300×200",
            "Неавтоклавный пенобетон D600 для перегородок и малоэтажного строительства.",
            "шт",
            18_500,
        ),
    ],
    "krovlya-fasad": [
        (
            "Профнастил С-21 оцинкованный 0,5 мм",
            "Профлист для кровли и заборов, резка в размер по заказу клиента.",
            "м²",
            68_000,
        ),
        (
            "Металлочерепица «Монтеррей» с полимерным покрытием",
            "Покрытие полиэстер, 12 цветов RAL. Комплектующие и доборные элементы в наличии.",
            "м²",
            79_000,
        ),
        (
            "Фасадные панели под камень",
            "Композитные панели для навесного фасада, крепёж в комплекте.",
            "м²",
            145_000,
        ),
    ],
    "metalloprokat": [
        (
            "Арматура А500С d12 мм",
            "Арматура рифлёная, длина 11,7 м. Резка и гибка по спецификации.",
            "т",
            9_400_000,
        ),
        (
            "Труба профильная 40×40×2",
            "Сварная профильная труба, длина 6 м. Остатки на складе — уточняйте.",
            "т",
            10_200_000,
        ),
    ],
    "chernye-metally": [
        (
            "Лист г/к 4 мм, 1500×6000",
            "Горячекатаный лист Ст3сп. Резка плазмой по чертежу.",
            "т",
            9_900_000,
        ),
        ("Швеллер 12П", "Швеллер с параллельными гранями полок, длина 12 м.", "т", 10_600_000),
        ("Уголок равнополочный 50×50×5", "Уголок стальной, длина 6 и 12 м.", "т", 9_700_000),
    ],
    "cvetnye-metally": [
        (
            "Медный катанка 8 мм",
            "Катанка медная М00, бухты по 2–3 тонны. Экспортные документы.",
            "т",
            112_000_000,
        ),
        (
            "Алюминиевый профиль АД31",
            "Профиль для окон и фасадных систем, анодирование под заказ.",
            "кг",
            54_000,
        ),
    ],
    "pryazha-tkani": [
        (
            "Хлопковая пряжа Ne 30/1 кардная",
            "Пряжа из узбекского хлопка, бобины по 1,89 кг. Партии от 1 тонны.",
            "кг",
            38_000,
        ),
        (
            "Ткань бязь 142 г/м², ширина 220 см",
            "Отбеленная и суровая бязь для постельного белья. Рулоны по 100 м.",
            "м",
            14_500,
        ),
        (
            "Трикотажное полотно кулирка 30/1",
            "Полотно для футболок, окраска в любой цвет от 300 кг.",
            "кг",
            62_000,
        ),
    ],
    "gotovaya-odezhda": [
        (
            "Футболки хлопковые базовые, оптом",
            "100% хлопок, плотность 180 г/м². Нанесение логотипа под заказ.",
            "шт",
            32_000,
        ),
        (
            "Спецодежда: костюм рабочий летний",
            "Куртка и полукомбинезон, ткань смесовая, светоотражающие полосы.",
            "комплект",
            185_000,
        ),
    ],
    "zerno-muka": [
        (
            "Мука пшеничная высшего сорта, 50 кг",
            "Мука для хлебопекарен и кондитерских, ГОСТ. Доставка по области.",
            "мешок",
            265_000,
        ),
        (
            "Пшеница продовольственная 3 класс",
            "Урожай текущего года, клейковина 24–26%. Отгрузка вагонами и автотранспортом.",
            "т",
            3_100_000,
        ),
    ],
    "sukhofrukty": [
        (
            "Изюм «Шиготой» сушёный",
            "Тёмный изюм высшего сорта, коробки по 10 кг. Экспортные партии.",
            "кг",
            34_000,
        ),
        (
            "Курага «Хурмаи» без косточки",
            "Абрикос натуральной сушки, без серы. Фасовка под заказ.",
            "кг",
            46_000,
        ),
        (
            "Грецкий орех, ядро светлое половинки",
            "Калибровка, вакуумная упаковка по 10 кг.",
            "кг",
            88_000,
        ),
    ],
    "produkty-drugoe": [
        (
            "Масло хлопковое рафинированное, 5 л",
            "Дезодорированное масло, ПЭТ-бутылки, паллета 120 шт.",
            "шт",
            98_000,
        ),
        ("Рис «Девзира» отборный", "Ферганский рис, мешки по 25 кг.", "кг", 29_000),
    ],
    "poddony-tara": [
        (
            "Поддон деревянный 1200×800 новый",
            "Европоддон, термообработка ISPM 15 для экспорта.",
            "шт",
            115_000,
        ),
        (
            "Поддон б/у 1000×1200 первый сорт",
            "Крепкие поддоны после одной поставки, отбор вручную.",
            "шт",
            62_000,
        ),
    ],
    "upakovka-drugoe": [
        (
            "Гофрокороб трёхслойный под заказ",
            "Короба любого размера, печать в 1–2 цвета. Тираж от 1000 штук.",
            "шт",
            3_800,
        ),
        ("Стрейч-плёнка 500 мм × 23 мкм", "Ручная стрейч-плёнка, рулон 1,5 кг.", "рулон", 42_000),
    ],
    "stanki": [
        (
            "Станок лазерной резки металла 3 кВт",
            "Оптоволоконный лазер, стол 3000×1500. Пусконаладка и обучение.",
            "шт",
            640_000_000,
        ),
        (
            "Ленточнопильный станок по металлу",
            "Резка под углом до 60°, гидравлическая подача.",
            "шт",
            58_000_000,
        ),
    ],
    "oborudovanie-drugoe": [
        (
            "Капельное орошение: комплект на 1 га",
            "Ленты, фильтры, магистраль и фитинги. Проект и монтаж.",
            "комплект",
            24_000_000,
        ),
        (
            "Дизельный генератор 100 кВт",
            "Генератор в шумозащитном кожухе, автозапуск, гарантия 2 года.",
            "шт",
            168_000_000,
        ),
    ],
    "ofisnaya-mebel": [
        (
            "Офисный стол 1400×700 ЛДСП",
            "Стол с тумбой на 3 ящика, цвет дуб сонома.",
            "шт",
            1_450_000,
        ),
        (
            "Кресло руководителя кожзам",
            "Механизм качания, газлифт класса 4, крестовина металл.",
            "шт",
            2_300_000,
        ),
        (
            "Шкаф для документов 800×400×2000",
            "Полузакрытый шкаф, 5 полок, стекло в верхней части.",
            "шт",
            1_900_000,
        ),
    ],
    "mebel-dlya-doma": [
        (
            "Кухонный гарнитур на заказ",
            "МДФ-фасады, фурнитура Blum. Замер и дизайн-проект бесплатно.",
            "пог. м",
            4_800_000,
        ),
        (
            "Шкаф-купе с зеркалом 1800 мм",
            "Корпус ЛДСП 16 мм, система раздвижных дверей.",
            "шт",
            5_600_000,
        ),
    ],
    "provedenie-vystavok": [
        (
            "Застройка выставочного стенда под ключ",
            "Проект, изготовление и монтаж стенда на выставках в Ташкенте.",
            "м²",
            1_200_000,
        ),
        (
            "Аренда выставочного оборудования",
            "Витрины, ресепшен-стойки, промостойки, свет.",
            "комплект",
            2_500_000,
        ),
    ],
    "gruzoperevozki": [
        (
            "Фура 20 т: Ташкент — Москва",
            "Тентованный полуприцеп 82 м³, страхование груза, отслеживание.",
            "рейс",
            52_000_000,
        ),
        (
            "Доставка сборных грузов по Узбекистану",
            "Отправка 2 раза в неделю во все областные центры.",
            "кг",
            1_200,
        ),
        (
            "Контейнер 40 футов из Китая (Урумчи)",
            "Ж/д доставка, таможенное оформление в Ташкенте.",
            "рейс",
            61_000_000,
        ),
    ],
    "skladskie-uslugi": [
        (
            "Ответственное хранение на складе класса B",
            "Тёплый склад, стеллажи, учёт в WMS, погрузка.",
            "паллета",
            95_000,
        ),
        (
            "Кросс-докинг и комплектация заказов",
            "Приёмка, сортировка и отгрузка в тот же день.",
            "паллета",
            60_000,
        ),
    ],
    "logistika-drugoe": [
        (
            "Таможенный брокер: оформление импорта",
            "Декларирование, сертификация, консультации по ТН ВЭД.",
            "шт",
            2_400_000,
        ),
    ],
    "hr-uslugi": [
        (
            "Подбор персонала: рабочие специальности",
            "Сварщики, монтажники, операторы станков. Гарантия замены 2 месяца.",
            "шт",
            3_500_000,
        ),
        (
            "Подбор менеджеров по продажам",
            "Поиск, оценка и проверка рекомендаций.",
            "шт",
            6_000_000,
        ),
    ],
    "finansy-buhgalteriya": [
        (
            "Бухгалтерское сопровождение ООО",
            "Учёт, отчётность в ГНК, зарплата. До 100 операций в месяц.",
            "шт",
            2_800_000,
        ),
        (
            "Аудит финансовой отчётности",
            "Обязательный и инициативный аудит, сроки от 2 недель.",
            "шт",
            15_000_000,
        ),
    ],
    "stroymaterialy-drugoe": [
        (
            "Сухая смесь: штукатурка гипсовая 30 кг",
            "Ручное и машинное нанесение, белая.",
            "мешок",
            64_000,
        ),
        (
            "Плиточный клей усиленный 25 кг",
            "Для керамогранита и уличных работ, класс C1.",
            "мешок",
            58_000,
        ),
    ],
}

#: Закупки: подкатегория → (название, описание, единица)
WANTED: dict[str, list[tuple[str, str, str]]] = {
    "cement-beton": [
        (
            "Куплю цемент М400 — 200 тонн ежемесячно",
            "Нужна стабильная поставка на объект в Ташкентской области, оплата по факту.",
            "т",
        )
    ],
    "pryazha-tkani": [
        (
            "Закупаем хлопковую пряжу Ne 20/1",
            "Для трикотажного производства, от 5 тонн в месяц. Предложения с образцами.",
            "кг",
        )
    ],
    "upakovka-drugoe": [
        (
            "Ищем поставщика гофрокоробов",
            "Короба под сухофрукты, 10 тысяч в месяц, печать логотипа.",
            "шт",
        )
    ],
    "gruzoperevozki": [
        (
            "Нужна перевозка: Фергана — Алматы",
            "Рефрижератор, 18 тонн сухофруктов, раз в две недели.",
            "рейс",
        )
    ],
    "ofisnaya-mebel": [
        (
            "Закупка офисной мебели на 40 рабочих мест",
            "Столы, кресла, шкафы. Нужна смета и сроки.",
            "комплект",
        )
    ],
    "zerno-muka": [
        ("Куплю муку высшего сорта", "Для хлебозавода, 60 тонн в месяц, доставка в Самарканд.", "т")
    ],
}

# ── Компании ─────────────────────────────────────────────────────────

#: name, legal_name, город, тип, роль, подкатегории, сотрудники, год, контакт, о себе
COMPANIES: list[dict[str, Any]] = [
    {
        "name": "Пулат Курилиш Материаллари",
        "legal": "ООО «Pulat Qurilish Materiallari»",
        "city": "tashkent",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["cement-beton", "stroymaterialy-drugoe"],
        "staff": "100-500",
        "year": 2009,
        "person": "Бахтиёр Пулатов",
        "about": "Производим цемент и сухие строительные смеси с 2009 года. Собственный автопарк, отгрузка в день оплаты.",
    },
    {
        "name": "Самарканд Гишт",
        "legal": "ООО «Samarqand G'isht»",
        "city": "samarkand",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["kirpich-blok"],
        "staff": "50-100",
        "year": 2014,
        "person": "Алишер Каримов",
        "about": "Кирпичный завод полного цикла. Выпускаем 40 млн штук кирпича в год.",
    },
    {
        "name": "Фасад Про",
        "legal": "ООО «Fasad Pro»",
        "city": "tashkent",
        "type": "distributor",
        "role": "both",
        "cats": ["krovlya-fasad"],
        "staff": "10-50",
        "year": 2017,
        "person": "Дмитрий Ким",
        "about": "Кровля и фасады: поставка, расчёт материала и монтаж бригадами.",
    },
    {
        "name": "Ангрен Металл Савдо",
        "legal": "ООО «Angren Metall Savdo»",
        "city": "tashkent",
        "type": "trader",
        "role": "supplier",
        "cats": ["metalloprokat", "chernye-metally"],
        "staff": "10-50",
        "year": 2012,
        "person": "Шерзод Рахимов",
        "about": "Металлобаза: арматура, лист, трубы, швеллер. Резка и доставка по Ташкенту.",
    },
    {
        "name": "Навоий Рангли Металл",
        "legal": "АО «Navoiy Rangli Metall»",
        "city": "navoiy",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["cvetnye-metally"],
        "staff": "500+",
        "year": 2001,
        "person": "Ойбек Усманов",
        "about": "Медная и алюминиевая продукция для кабельных и строительных заводов.",
    },
    {
        "name": "Фергана Текстиль Групп",
        "legal": "ООО «Farg'ona Tekstil Group»",
        "city": "fergana",
        "type": "manufacturer",
        "role": "both",
        "cats": ["pryazha-tkani"],
        "staff": "100-500",
        "year": 2011,
        "person": "Дилноза Юсупова",
        "about": "Прядильно-ткацкая фабрика: пряжа, бязь, трикотажное полотно. Работаем на экспорт.",
    },
    {
        "name": "Андижан Тикув",
        "legal": "ООО «Andijon Tikuv»",
        "city": "andijan",
        "type": "manufacturer",
        "role": "both",
        "cats": ["gotovaya-odezhda", "pryazha-tkani"],
        "staff": "50-100",
        "year": 2016,
        "person": "Нодира Ахмедова",
        "about": "Швейное производство: трикотаж, спецодежда, пошив под вашей маркой.",
    },
    {
        "name": "Зарафшон Дон",
        "legal": "ООО «Zarafshon Don»",
        "city": "bukhara",
        "type": "manufacturer",
        "role": "both",
        "cats": ["zerno-muka"],
        "staff": "50-100",
        "year": 2008,
        "person": "Фарход Назаров",
        "about": "Мукомольный комбинат и элеватор на 20 тысяч тонн.",
    },
    {
        "name": "Бухоро Мевалари",
        "legal": "ООО «Buxoro Mevalari»",
        "city": "bukhara",
        "type": "trader",
        "role": "both",
        "cats": ["sukhofrukty"],
        "staff": "10-50",
        "year": 2015,
        "person": "Жасур Хакимов",
        "about": "Сухофрукты и орехи на экспорт: Россия, Казахстан, Европа. Собственный цех сортировки.",
    },
    {
        "name": "Наманган Агро Экспорт",
        "legal": "ООО «Namangan Agro Eksport»",
        "city": "namangan",
        "type": "trader",
        "role": "supplier",
        "cats": ["sukhofrukty", "produkty-drugoe"],
        "staff": "10-50",
        "year": 2019,
        "person": "Улугбек Мирзаев",
        "about": "Агропродукция Наманганской области: сухофрукты, рис, масло.",
    },
    {
        "name": "Эко Тара",
        "legal": "ЧП «Eko Tara»",
        "city": "tashkent",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["poddony-tara"],
        "staff": "10-50",
        "year": 2018,
        "person": "Руслан Абдуллаев",
        "about": "Новые и восстановленные поддоны, экспортная термообработка.",
    },
    {
        "name": "Гофра Пак Жиззах",
        "legal": "ООО «Gofra Pak»",
        "city": "jizzakh",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["upakovka-drugoe"],
        "staff": "50-100",
        "year": 2020,
        "person": "Азиз Тошев",
        "about": "Гофрокартон и упаковка с печатью для пищевых и промышленных производств.",
    },
    {
        "name": "Станок Маркет",
        "legal": "ООО «Stanok Market»",
        "city": "tashkent",
        "type": "importer",
        "role": "supplier",
        "cats": ["stanki"],
        "staff": "10-50",
        "year": 2013,
        "person": "Евгений Цой",
        "about": "Металлообрабатывающие станки из Китая и Турции. Склад запчастей и сервисная служба.",
    },
    {
        "name": "Агротехника Сервис",
        "legal": "ООО «Agrotexnika Servis»",
        "city": "gulistan",
        "type": "distributor",
        "role": "supplier",
        "cats": ["oborudovanie-drugoe"],
        "staff": "10-50",
        "year": 2015,
        "person": "Сардор Эргашев",
        "about": "Системы орошения, генераторы, насосы. Проектирование и монтаж.",
    },
    {
        "name": "Офис Мебель Плюс",
        "legal": "ООО «Ofis Mebel Plyus»",
        "city": "tashkent",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["ofisnaya-mebel"],
        "staff": "50-100",
        "year": 2010,
        "person": "Анвар Исмаилов",
        "about": "Офисная мебель собственного производства, комплектация офисов под ключ.",
    },
    {
        "name": "Уютный Дом Наманган",
        "legal": "ЧП «Shinam Uy»",
        "city": "namangan",
        "type": "manufacturer",
        "role": "supplier",
        "cats": ["mebel-dlya-doma"],
        "staff": "10-50",
        "year": 2017,
        "person": "Комил Валиев",
        "about": "Кухни и шкафы на заказ по индивидуальным размерам.",
    },
    {
        "name": "Экспо Стенд",
        "legal": "ООО «Ekspo Stend»",
        "city": "tashkent",
        "type": "service",
        "role": "supplier",
        "cats": ["provedenie-vystavok"],
        "staff": "10-50",
        "year": 2012,
        "person": "Марина Ли",
        "about": "Выставочные стенды и оборудование для выставок в Узбекистане и Казахстане.",
    },
    {
        "name": "Шёлковый Путь Логистик",
        "legal": "ООО «Ipak Yo'li Logistik»",
        "city": "tashkent",
        "type": "service",
        "role": "supplier",
        "cats": ["gruzoperevozki", "logistika-drugoe"],
        "staff": "50-100",
        "year": 2011,
        "person": "Тимур Саидов",
        "about": "Международные автоперевозки, ж/д контейнеры из Китая, таможенное оформление.",
    },
    {
        "name": "Склад Сити",
        "legal": "ООО «Sklad Siti»",
        "city": "tashkent",
        "type": "service",
        "role": "supplier",
        "cats": ["skladskie-uslugi"],
        "staff": "10-50",
        "year": 2016,
        "person": "Ирина Пак",
        "about": "Склад класса B у кольцевой дороги, 12 000 паллетомест.",
    },
    {
        "name": "Кадры Про",
        "legal": "ООО «Kadrlar Pro»",
        "city": "tashkent",
        "type": "service",
        "role": "supplier",
        "cats": ["hr-uslugi"],
        "staff": "1-10",
        "year": 2019,
        "person": "Гульнора Рашидова",
        "about": "Кадровое агентство: рабочие специальности и коммерческий персонал.",
    },
    {
        "name": "Баланс Аудит",
        "legal": "ООО «Balans Audit»",
        "city": "samarkand",
        "type": "service",
        "role": "supplier",
        "cats": ["finansy-buhgalteriya"],
        "staff": "10-50",
        "year": 2007,
        "person": "Шахноза Абдуллаева",
        "about": "Аудит и бухгалтерское сопровождение для малого и среднего бизнеса.",
    },
    {
        "name": "Хоразм Пахта Савдо",
        "legal": "ООО «Xorazm Paxta Savdo»",
        "city": "urgench",
        "type": "trader",
        "role": "buyer",
        "cats": ["pryazha-tkani"],
        "staff": "10-50",
        "year": 2014,
        "person": "Отабек Курбанов",
        "about": "Закупаем пряжу и ткани для швейных цехов Хорезма.",
    },
    {
        "name": "Термез Транзит",
        "legal": "ООО «Termiz Tranzit»",
        "city": "termez",
        "type": "service",
        "role": "both",
        "cats": ["gruzoperevozki"],
        "staff": "10-50",
        "year": 2018,
        "person": "Бобур Тураев",
        "about": "Перевозки через южные пограничные переходы, экспедирование.",
    },
    {
        "name": "Каракалпак Строй Снаб",
        "legal": "ООО «Qoraqalpoq Qurilish Ta'minot»",
        "city": "nukus",
        "type": "distributor",
        "role": "buyer",
        "cats": ["stroymaterialy-drugoe", "cement-beton"],
        "staff": "10-50",
        "year": 2013,
        "person": "Ерлан Бекмуратов",
        "about": "Снабжаем строительные объекты Каракалпакстана, закупаем крупным оптом.",
    },
]

#: Кто на кого оставил отзыв: (компания, автор, оценка, текст) — номера в COMPANIES
REVIEWS: list[tuple[int, int, int, str]] = [
    (
        0,
        23,
        5,
        "Берём цемент второй год: документы всегда в порядке, машины приходят в назначенный день.",
    ),
    (
        0,
        2,
        4,
        "Хорошее качество смесей. Один раз задержали отгрузку на сутки, предупредили заранее.",
    ),
    (
        1,
        23,
        5,
        "Кирпич ровный, бой при доставке минимальный. Цена ниже рынка при объёме от вагона.",
    ),
    (3, 14, 5, "Резали лист по нашим чертежам — точно и быстро. Будем работать дальше."),
    (3, 12, 4, "Нормальная металлобаза, есть всё ходовое. Доставка по городу в тот же день."),
    (5, 21, 5, "Пряжа стабильного качества, лабораторные протоколы прикладывают к каждой партии."),
    (5, 6, 4, "Качество хорошее, но минимальная партия великовата для небольшого цеха."),
    (6, 19, 5, "Пошили спецодежду с логотипом для нашей компании, всё в срок."),
    (8, 17, 5, "Отправили три фуры сухофруктов в Москву — упаковка и документы на высоте."),
    (8, 9, 4, "Надёжный партнёр по экспорту, всегда на связи."),
    (10, 11, 5, "Поддоны для экспорта с клеймом, проблем на таможне не было."),
    (11, 8, 5, "Делают короба с печатью под наши сухофрукты, качество печати отличное."),
    (12, 3, 4, "Купили ленточнопильный станок: пусконаладка за день, обучили операторов."),
    (14, 18, 5, "Обставили офис на 30 мест за три недели, сборка аккуратная."),
    (17, 8, 5, "Возят наши грузы в Россию и Казахстан, отслеживание работает, цены честные."),
    (17, 9, 4, "Сроки соблюдают, на границе помогли с документами."),
    (18, 13, 5, "Храним оборудование на их складе — учёт прозрачный, отчёты каждую неделю."),
    (19, 4, 4, "Нашли трёх сварщиков за две недели, один не прошёл испытательный срок — заменили."),
    (20, 15, 5, "Ведут бухгалтерию третий год, ни одного штрафа от налоговой."),
]


# ── Запись ───────────────────────────────────────────────────────────


def _rows(query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])

        return list(cursor.fetchall())


def _insert(table: str, values: dict[str, Any]) -> int:
    columns = list(values)
    with connection.cursor() as cursor:
        cursor.execute(
            f"insert into {table} ({', '.join(columns)}) "
            f"values ({', '.join(['%s'] * len(columns))}) returning id",
            [values[c] for c in columns],
        )
        (pk,) = cursor.fetchone()

    return int(pk)


def _ids(table: str, slugs: set[str]) -> dict[str, int]:
    rows = _rows(f"select id, slug from {table} where slug = any(%s)", [list(slugs)])

    return {slug: pk for pk, slug in rows}


def _company_slug(name: str) -> str:
    base = slugify(name)[:60].strip("-") or "company"
    slug, n = base, 2

    while _rows("select 1 from companies where slug = %s limit 1", [slug]):
        slug, n = f"{base}-{n}", n + 1

    return slug


def refused() -> str | None:
    """Почему демо-данные сюда нельзя, или None."""
    if os.environ.get("APP_ENV", "local") == "production":
        return "Боевой сайт (APP_ENV=production): демо-данные только для тестового."

    return None


def seed(*, now: datetime | None = None) -> dict[str, int]:
    """Завести демо-данные; уже заведены — ничего. Итог — сколько чего заведено."""
    from savdex import schedule
    from savdex.web import guard

    if (why := refused()) is not None:
        raise DemoRefusedError(why)

    made = {"companies": 0, "users": 0, "listings": 0, "reviews": 0}

    if _rows("select 1 from companies where source_note = %s limit 1", [MARK]):
        return made

    now = now or datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    rng = random.Random(2026)
    country = _rows("select id from countries where code = 'uz'")
    if not country:
        raise DemoRefusedError("Нет справочников (страна uz) — сначала manage.py seed.")

    country_id = int(country[0][0])
    leaf = {c for company in COMPANIES for c in company["cats"]}
    categories = _ids("categories", leaf)
    cities = _ids("cities", {company["city"] for company in COMPANIES})
    missing = sorted((leaf - set(categories)) | ({c["city"] for c in COMPANIES} - set(cities)))
    if missing:
        raise DemoRefusedError(f"Нет справочников: {', '.join(missing)} — сначала manage.py seed.")

    owners: list[int] = []
    company_ids: list[int] = []

    with transaction.atomic():
        for n, data in enumerate(COMPANIES, start=1):
            created = now - timedelta(days=30 + rng.randint(0, 600))
            city_id = cities[data["city"]]
            company_id = _insert(
                "companies",
                {
                    "slug": _company_slug(data["name"]),
                    "name": data["name"],
                    "legal_name": data["legal"],
                    "legal_form": "legal",
                    "tin": str(300_000_000 + n * 7919),
                    "country_id": country_id,
                    "city_id": city_id,
                    "type": data["type"],
                    "primary_role": data["role"],
                    "description": data["about"],
                    "phone": f"+998 71 200 {n:02d} {n * 3 % 100:02d}",
                    "email": f"info@{slugify(data['name'])[:40]}.{EMAIL_DOMAIN}",
                    "contact_person": data["person"],
                    "founded_year": data["year"],
                    "employees_range": data["staff"],
                    "verification_level": rng.choice((0, 1, 1, 2)),
                    "rating": 0,
                    "reviews_count": 0,
                    "completed_deals_count": rng.randint(3, 140),
                    "response_time_hours": rng.randint(1, 24),
                    "status": "active",
                    "search_text": index(f"{data['name']} {data['legal']}"),
                    "source_note": MARK,
                    "created_at": created,
                    "updated_at": created,
                },
            )
            company_ids.append(company_id)
            owners.append(
                _insert(
                    "users",
                    {
                        "name": data["person"],
                        "email": f"demo-{n}@{EMAIL_DOMAIN}",
                        "email_verified_at": created,
                        # Пароль, которого никто не знает: под демо-учётками не входят
                        "password": guard.make(secrets.token_urlsafe(24)),
                        "company_id": company_id,
                        "company_role": "owner",
                        "account_type": "legal",
                        "locale": "ru",
                        "status": "active",
                        "must_change_password": False,
                        "created_at": created,
                        "updated_at": created,
                    },
                )
            )

            for slug in data["cats"]:
                _insert(
                    "company_category",
                    {"company_id": company_id, "category_id": categories[slug]},
                )

            # Поставщик — до четырёх предложений, закупщик — одна закупка, «и то,
            # и другое» — оба
            offers = [(s, item) for s in data["cats"] for item in CATALOG.get(s, [])]
            wanted = [(s, item) for s in data["cats"] for item in WANTED.get(s, [])]
            if data["role"] == "buyer":
                offers = []
            if data["role"] == "supplier":
                wanted = []

            for slug, (title, about, unit, price) in offers[:4]:
                cost = round(price * rng.uniform(0.9, 1.15), -2)
                made["listings"] += _listing(
                    (company_id, owners[-1], categories[slug], city_id),
                    ("supply", title, about, unit, cost),
                    now,
                    rng,
                )
            for slug, (title, about, unit) in wanted[:1]:
                made["listings"] += _listing(
                    (company_id, owners[-1], categories[slug], city_id),
                    ("demand", title, about, unit, None),
                    now,
                    rng,
                )

        made["companies"] = len(company_ids)
        made["users"] = len(owners)

        for target, author, rating, body in REVIEWS:
            stamp = now - timedelta(days=rng.randint(2, 200))
            _insert(
                "reviews",
                {
                    "company_id": company_ids[target],
                    "author_company_id": company_ids[author],
                    "author_user_id": owners[author],
                    "rating": rating,
                    "rating_description": rating,
                    "rating_response": max(3, rating - rng.randint(0, 1)),
                    "rating_deadlines": rating,
                    "rating_quality": rating,
                    "body": body,
                    "deal_confirmed": True,
                    "status": "published",
                    "created_at": stamp,
                    "updated_at": stamp,
                },
            )
            made["reviews"] += 1

        # Рейтинг — тем же пересчётом, что ночное расписание
        schedule.recalculate_ratings(now, now)

    return made


def _listing(
    owner: tuple[int, int, int, int],
    offer: tuple[str, str, str, str, float | None],
    now: datetime,
    rng: random.Random,
) -> int:
    """Опубликованное объявление: (компания, владелец, категория, город), (вид, …)."""
    company_id, user_id, category_id, city_id = owner
    kind, title, about, unit, price = offer
    published = now - timedelta(days=rng.randint(1, 50), hours=rng.randint(0, 23))
    pk = _insert(
        "listings",
        {
            "company_id": company_id,
            "user_id": user_id,
            "category_id": category_id,
            "city_id": city_id,
            "type": kind,
            "title": title,
            "description": about,
            "price": price,
            "currency": "UZS",
            "unit": unit,
            "price_negotiable": price is None,
            "status": "active",
            "wizard_step": 4,
            "published_at": published,
            "expires_at": now + timedelta(days=rng.randint(20, 85)),
            "impressions_count": rng.randint(40, 2500),
            "views_count": rng.randint(5, 400),
            "unlocks_count": rng.randint(0, 25),
            "search_text": index(f"{title} {about}"),
            "source": "cabinet",
            "created_at": published,
            "updated_at": published,
        },
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "update listings set slug = %s where id = %s", [numbered_slug(title, pk), pk]
        )

    return 1
