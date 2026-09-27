<?php

/*
 * Тексты страниц «О компании», «Помощь», «Инструкция» и «Правила» —
 * такими, какими их показывал сайт, когда они жили в словарях
 * lang/<язык>/ui.php (раздел about). Их один раз переносит в базу
 * миграция 2026_09_28_160000_pages_from_dictionaries; дальше тексты
 * правят в админке, и этот файл — только история переноса.
 *
 * Разметка текста — App\Support\PageBody.
 */
return [
    'pages' => [
        'about' => [
            'ru' => [
                'title' => 'О компании',
                'excerpt' => 'SAVDEX — площадка, на которой поставщики и закупщики находят друг друга напрямую.',
                'body' => 'Мы работаем в Узбекистане и Центральной Азии. Компании публикуют, что могут поставить или что хотят купить, находят партнёра и договариваются между собой. Площадка не участвует в переговорах, не берёт процент со сделки и не проводит через себя деньги.

Зарабатываем мы на подписке и доступе к контактам. Наш доход не зависит от суммы вашего контракта.',
            ],
            'uz' => [
                'title' => 'Kompaniya haqida',
                'excerpt' => 'SAVDEX — yetkazib beruvchilar va xaridorlar bir-birini to‘g‘ridan-to‘g‘ri topadigan maydon.',
                'body' => 'Biz O‘zbekiston va Markaziy Osiyoda ishlaymiz. Kompaniyalar nimani yetkazib bera olishini yoki nimani sotib olmoqchi ekanini e’lon qiladi, hamkor topadi va o‘zaro kelishadi. Maydon muzokaralarda qatnashmaydi, bitimdan foiz olmaydi va pulni o‘zi orqali o‘tkazmaydi.

Biz obuna va kontaktlarga kirishdan daromad olamiz. Daromadimiz shartnomangiz summasiga bog‘liq emas.',
            ],
            'en' => [
                'title' => 'About the company',
                'excerpt' => 'SAVDEX is a marketplace where suppliers and buyers find each other directly.',
                'body' => 'We work in Uzbekistan and Central Asia. Companies publish what they can supply or what they want to buy, find a partner and agree between themselves. The platform takes no part in the talks, takes no percentage of the deal and never handles the money.

We earn from subscriptions and access to contacts. Our income does not depend on the size of your contract.',
            ],
            'zh' => [
                'title' => '关于公司',
                'excerpt' => 'SAVDEX 是供应商与采购商直接找到彼此的平台。',
                'body' => '我们在乌兹别克斯坦和中亚开展业务。企业发布自己能供应什么或想采购什么，找到伙伴并自行商谈。平台不参与谈判，不抽取交易佣金，也不经手资金。

我们的收入来自订阅和联系方式的解锁，与您的合同金额无关。',
            ],
            'tr' => [
                'title' => 'Şirket hakkında',
                'excerpt' => 'SAVDEX, tedarikçiler ile alıcıların birbirini doğrudan bulduğu bir platformdur.',
                'body' => 'Özbekistan ve Orta Asya’da çalışıyoruz. Şirketler ne tedarik edebileceğini ya da ne almak istediğini yayımlar, ortağını bulur ve kendi aralarında anlaşır. Platform görüşmelere katılmaz, işlemden pay almaz ve parayı kendi üzerinden geçirmez.

Gelirimiz abonelik ve iletişim bilgilerine erişimden gelir. Kazancımız sözleşmenizin tutarına bağlı değildir.',
            ],
        ],
        'contacts' => [
            'ru' => [
                'title' => 'Контакты',
                'excerpt' => '',
                'body' => 'Приезжайте, если вопрос проще решить лично. Договоры и документы принимаем и по почте — приезжать ради подписи необязательно.',
            ],
            'uz' => [
                'title' => 'Aloqa',
                'excerpt' => '',
                'body' => 'Savolni shaxsan hal qilish osonroq bo‘lsa, kelavering. Shartnoma va hujjatlarni pochta orqali ham qabul qilamiz — imzo uchun kelish shart emas.',
            ],
            'en' => [
                'title' => 'Contacts',
                'excerpt' => '',
                'body' => 'Come over if a question is easier to settle in person. We also accept contracts and documents by post — there is no need to travel just for a signature.',
            ],
            'zh' => [
                'title' => '联系方式',
                'excerpt' => '',
                'body' => '如果当面解决更方便，欢迎来访。合同和文件也可以邮寄办理 — 不必仅为签字专程前来。',
            ],
            'tr' => [
                'title' => 'İletişim',
                'excerpt' => '',
                'body' => 'Konuyu yüz yüze çözmek daha kolaysa buyurun gelin. Sözleşme ve belgeleri posta ile de alıyoruz — yalnızca imza için yola çıkmak gerekmez.',
            ],
        ],
        'help' => [
            'ru' => [
                'title' => 'Помощь',
                'excerpt' => 'Ответы на вопросы, которые задают чаще всего. Не нашли свой — напишите в поддержку.',
                'body' => '',
            ],
            'uz' => [
                'title' => 'Yordam',
                'excerpt' => 'Eng ko‘p beriladigan savollarga javoblar. O‘z savolingizni topmadingizmi — qo‘llab-quvvatlash xizmatiga yozing.',
                'body' => '',
            ],
            'en' => [
                'title' => 'Help',
                'excerpt' => 'Answers to the questions we hear most often. Didn’t find yours? Write to support.',
                'body' => '',
            ],
            'zh' => [
                'title' => '帮助',
                'excerpt' => '最常见问题的解答。没有找到您的问题？请联系客服。',
                'body' => '',
            ],
            'tr' => [
                'title' => 'Yardım',
                'excerpt' => 'En sık sorulan soruların yanıtları. Sorunuzu bulamadıysanız destek ekibine yazın.',
                'body' => '',
            ],
        ],
        'guide' => [
            'ru' => [
                'title' => 'Инструкция использования',
                'excerpt' => 'Как начать работать с площадкой — поставщику и закупщику.',
                'body' => '## Если вы поставщик

1. Зарегистрируйтесь и подтвердите почту.
До подтверждения кабинет доступен, но публиковать нельзя.
2. Заполните карточку компании.
Заполненный профиль получает втрое больше обращений.
3. Разместите объявление.
Укажите точную марку и объём — по ним ищут. Объявления с ценой смотрят в 2,4 раза чаще.
4. Следите за входящими.
Видно, какая компания открыла ваши контакты и по какому объявлению.

## Если вы закупщик

1. Найдите в каталоге или опубликуйте запрос.
Каталог виден целиком без оплаты.
2. Изучите компанию до звонка.
Документы, рейтинг, отзывы, срок на площадке — всё открыто.
3. Откройте контакт.
Кредит списывается за компанию, а не за объявление.',
            ],
            'uz' => [
                'title' => 'Foydalanish qo‘llanmasi',
                'excerpt' => 'Platformada ishni qanday boshlash kerak — yetkazib beruvchi va xaridor uchun.',
                'body' => '## Agar siz yetkazib beruvchi bo‘lsangiz

1. Ro‘yxatdan o‘ting va pochtani tasdiqlang.
Tasdiqlanmaguncha kabinet ochiq, lekin e’lon joylashtirib bo‘lmaydi.
2. Kompaniya kartasini to‘ldiring.
To‘ldirilgan profil uch barobar ko‘p murojaat oladi.
3. E’lon joylashtiring.
Aniq marka va hajmni ko‘rsating — qidiruv shular bo‘yicha boradi. Narxi ko‘rsatilgan e’lonlar 2,4 barobar ko‘p ochiladi.
4. Kiruvchi murojaatlarni kuzating.
Qaysi kompaniya kontaktlaringizni va qaysi e’lon bo‘yicha ochgani ko‘rinadi.

## Agar siz xaridor bo‘lsangiz

1. Katalogdan toping yoki so‘rov joylashtiring.
Katalog to‘liq, to‘lovsiz ko‘rinadi.
2. Qo‘ng‘iroqdan oldin kompaniyani o‘rganing.
Hujjatlar, reyting, sharhlar, maydondagi muddat — hammasi ochiq.
3. Kontaktni oching.
Kredit e’lon uchun emas, kompaniya uchun yechiladi.',
            ],
            'en' => [
                'title' => 'How to use the platform',
                'excerpt' => 'How to get started on the platform — for suppliers and buyers.',
                'body' => '## If you are a supplier

1. Sign up and confirm your email.
The dashboard works before confirmation, but publishing does not.
2. Fill in your company profile.
A complete profile gets three times more enquiries.
3. Post a listing.
Give the exact grade and volume — that is what people search by. Listings with a price are viewed 2.4 times more often.
4. Watch your incoming requests.
You see which company unlocked your contacts and from which listing.

## If you are a buyer

1. Search the catalogue or post a request.
The whole catalogue is visible without paying.
2. Study the company before you call.
Documents, rating, reviews, time on the platform — all of it is open.
3. Unlock the contact.
A credit is spent per company, not per listing.',
            ],
            'zh' => [
                'title' => '使用指南',
                'excerpt' => '如何开始使用平台——供应商与采购方指南。',
                'body' => '## 如果您是供应商

1. 注册并验证邮箱。
验证前可以使用后台，但无法发布。
2. 填写企业资料。
资料完整的企业收到的询盘多三倍。
3. 发布信息。
写明确切的牌号与数量 — 买家正是按此搜索。标价的信息被查看的次数多 2.4 倍。
4. 关注收到的询盘。
可以看到哪家企业从哪条信息解锁了您的联系方式。

## 如果您是采购商

1. 在目录中查找，或发布采购需求。
整个目录无需付费即可浏览。
2. 致电前先了解该企业。
文件、评分、评价、入驻时长 — 全部公开。
3. 解锁联系方式。
额度按企业扣除，而非按信息条数。',
            ],
            'tr' => [
                'title' => 'Kullanım kılavuzu',
                'excerpt' => 'Platformda nasıl başlanır — tedarikçiler ve alıcılar için.',
                'body' => '## Tedarikçiyseniz

1. Kayıt olun ve e-postanızı doğrulayın.
Doğrulamadan önce panel açıktır, ancak ilan yayımlanamaz.
2. Şirket kartınızı doldurun.
Eksiksiz profil üç kat daha fazla başvuru alır.
3. İlan yayımlayın.
Tam markayı ve hacmi yazın — arama bunlarla yapılır. Fiyatı olan ilanlara 2,4 kat daha sık bakılır.
4. Gelen talepleri izleyin.
Hangi şirketin iletişim bilgilerinizi hangi ilandan açtığı görünür.

## Alıcıysanız

1. Katalogdan bulun ya da bir talep yayımlayın.
Katalog ödeme yapmadan tümüyle görünür.
2. Aramadan önce şirketi inceleyin.
Belgeler, puan, yorumlar, platformdaki süre — hepsi açıktır.
3. İletişim bilgisini açın.
Kredi ilan başına değil, şirket başına düşer.',
            ],
        ],
        'rules' => [
            'ru' => [
                'title' => 'Правила размещения',
                'excerpt' => 'Что можно и что нельзя публиковать на площадке.',
                'body' => '! Контактные данные в тексте объявления запрещены.
Телефон, почта, ссылки и ники в мессенджерах автоматически скрываются. Контакты передаются только через раскрытие контактов — на этом работает площадка.

## Что обязательно

- Достоверные название, ИНН и адрес компании
- Объявление в подходящей категории
- Реальные условия поставки, оплаты и объёмов
- Снятие объявления, когда товар закончился',
            ],
            'uz' => [
                'title' => 'Joylashtirish qoidalari',
                'excerpt' => 'Platformada nimani joylash mumkin va nimani mumkin emas.',
                'body' => '! E’lon matnida aloqa ma’lumotlari taqiqlanadi.
Telefon, pochta, havolalar va messenjerdagi nomlar avtomatik yashiriladi. Kontaktlar faqat kontakt ochish orqali beriladi — maydon shunga asoslanadi.

## Nima majburiy

- Kompaniyaning haqiqiy nomi, STIRi va manzili
- Mos toifadagi e’lon
- Yetkazib berish, to‘lov va hajmning haqiqiy shartlari
- Tovar tugaganda e’lonni olib tashlash',
            ],
            'en' => [
                'title' => 'Posting rules',
                'excerpt' => 'What you can and cannot publish on the platform.',
                'body' => '! Contact details in the listing text are not allowed.
Phone numbers, emails, links and messenger handles are hidden automatically. Contacts are passed only through contact unlocking — that is what the platform runs on.

## What is required

- A truthful company name, tax ID and address
- A listing in the right category
- Real terms of delivery, payment and volume
- Taking the listing down when the goods run out',
            ],
            'zh' => [
                'title' => '发布规则',
                'excerpt' => '平台上可以发布和禁止发布的内容。',
                'body' => '! 信息正文中禁止出现联系方式。
电话、邮箱、链接和即时通讯账号会被自动隐藏。联系方式仅通过解锁传递 — 平台正是依此运转。

## 必须做到

- 真实的企业名称、税号与地址
- 归入合适类别的信息
- 真实的交付、付款与数量条件
- 货品售罄时撤下信息',
            ],
            'tr' => [
                'title' => 'İlan kuralları',
                'excerpt' => 'Platformda neleri yayımlayabilir, neleri yayımlayamazsınız.',
                'body' => '! İlan metninde iletişim bilgisi yasaktır.
Telefon, e-posta, bağlantılar ve mesajlaşma kullanıcı adları otomatik olarak gizlenir. İletişim bilgileri yalnızca iletişim açma yoluyla verilir — platform buna dayanır.

## Zorunlu olanlar

- Şirketin gerçek unvanı, vergi numarası ve adresi
- Uygun kategoride bir ilan
- Gerçek teslimat, ödeme ve hacim koşulları
- Ürün bittiğinde ilanın kaldırılması',
            ],
        ],
    ],
    'faq' => [
        0 => [
            'ru' => [
                'question' => 'Сколько стоит разместить объявление?',
                'answer' => 'Размещение бесплатно на всех тарифах. Бесплатный тариф даёт 4 активных объявления и 3 раскрытия контактов в месяц.',
            ],
            'uz' => [
                'question' => 'E’lon joylashtirish qancha turadi?',
                'answer' => 'Joylashtirish barcha tariflarda bepul. Bepul tarif oyiga 4 ta faol e’lon va 3 marta kontakt ochish imkonini beradi.',
            ],
            'en' => [
                'question' => 'How much does posting a listing cost?',
                'answer' => 'Posting is free on every plan. The free plan gives 4 active listings and 3 contact unlocks per month.',
            ],
            'zh' => [
                'question' => '发布一条信息要多少钱？',
                'answer' => '所有套餐均可免费发布。免费套餐每月提供 4 条有效信息和 3 次联系方式解锁。',
            ],
            'tr' => [
                'question' => 'İlan yayımlamak ne kadar tutuyor?',
                'answer' => 'Yayımlamak tüm tarifelerde ücretsizdir. Ücretsiz tarife ayda 4 aktif ilan ve 3 iletişim açma hakkı verir.',
            ],
        ],
        1 => [
            'ru' => [
                'question' => 'Почему контакты платные?',
                'answer' => 'Мы не берём процент со сделок, поэтому доступ к контактам — единственный источник дохода площадки. Открыв контакт компании один раз, вы видите его навсегда по всем её объявлениям.',
            ],
            'uz' => [
                'question' => 'Nega kontaktlar pullik?',
                'answer' => 'Biz bitimlardan foiz olmaymiz, shuning uchun kontaktlarga kirish — maydonning yagona daromad manbai. Kompaniya kontaktini bir marta ochsangiz, uning barcha e’lonlarida umrbod ko‘rinadi.',
            ],
            'en' => [
                'question' => 'Why are contacts paid?',
                'answer' => 'We take no percentage of deals, so access to contacts is the platform’s only source of income. Unlock a company’s contact once and you keep it for good, across all of its listings.',
            ],
            'zh' => [
                'question' => '为什么联系方式要付费？',
                'answer' => '我们不抽取交易佣金，因此解锁联系方式是平台唯一的收入来源。解锁某家企业的联系方式后，其全部信息中都将长期可见。',
            ],
            'tr' => [
                'question' => 'İletişim bilgileri neden ücretli?',
                'answer' => 'İşlemlerden pay almıyoruz, bu yüzden iletişim bilgilerine erişim platformun tek gelir kaynağıdır. Bir şirketin iletişim bilgisini bir kez açtığınızda, onun tüm ilanlarında kalıcı olarak görürsünüz.',
            ],
        ],
        2 => [
            'ru' => [
                'question' => 'Что делать, если контакт нерабочий?',
                'answer' => 'Нажмите «Пожаловаться на контакт» в разделе «Мои контакты». Проверим за 2 рабочих дня; при подтверждении вернём кредит и снизим компании индекс отзывчивости.',
            ],
            'uz' => [
                'question' => 'Kontakt ishlamasa nima qilish kerak?',
                'answer' => '«Mening kontaktlarim» bo‘limida «Kontakt haqida shikoyat» tugmasini bosing. 2 ish kunida tekshiramiz; tasdiqlansa, kreditni qaytaramiz va kompaniyaning javob berish ko‘rsatkichini pasaytiramiz.',
            ],
            'en' => [
                'question' => 'What if a contact does not work?',
                'answer' => 'Press “Report contact” in the “My contacts” section. We check within 2 business days; if confirmed, we return the credit and lower the company’s responsiveness score.',
            ],
            'zh' => [
                'question' => '联系方式无法接通怎么办？',
                'answer' => '在「我的联系方式」中点击「举报联系方式」。我们将在 2 个工作日内核查；情况属实将退回额度，并下调该企业的响应评分。',
            ],
            'tr' => [
                'question' => 'İletişim bilgisi çalışmıyorsa ne yapmalı?',
                'answer' => '«İletişim bilgilerim» bölümünde «İletişimi bildir» düğmesine basın. 2 iş günü içinde kontrol ederiz; doğrulanırsa krediyi iade eder ve şirketin yanıt verme puanını düşürürüz.',
            ],
        ],
        3 => [
            'ru' => [
                'question' => 'Как получить бейдж «Проверена»?',
                'answer' => 'Загрузите свидетельство о регистрации и подтвердите ИНН. Модератор проверит: на Free и Flash — до 5 рабочих дней, на Business и Premium — 1 рабочий день. Бейдж не продаётся.',
            ],
            'uz' => [
                'question' => '«Tekshirilgan» belgisini qanday olish mumkin?',
                'answer' => 'Ro‘yxatdan o‘tish guvohnomasini yuklang va STIRni tasdiqlang. Moderator tekshiradi: Free va Flash tariflarida 5 ish kunigacha, Business va Premiumda 1 ish kuni. Belgi sotilmaydi.',
            ],
            'en' => [
                'question' => 'How do I get the “Verified” badge?',
                'answer' => 'Upload the certificate of registration and confirm the tax ID. A moderator checks it: up to 5 business days on Free and Flash, 1 business day on Business and Premium. The badge is not for sale.',
            ],
            'zh' => [
                'question' => '如何获得「已核验」标识？',
                'answer' => '上传注册证书并确认税号。审核员会进行核查：Free 与 Flash 套餐最长 5 个工作日，Business 与 Premium 为 1 个工作日。该标识不出售。',
            ],
            'tr' => [
                'question' => '«Doğrulanmış» rozeti nasıl alınır?',
                'answer' => 'Kayıt belgesini yükleyin ve vergi numarasını doğrulayın. Moderatör kontrol eder: Free ve Flash’ta 5 iş gününe kadar, Business ve Premium’da 1 iş günü. Rozet satılık değildir.',
            ],
        ],
        4 => [
            'ru' => [
                'question' => 'Какими картами можно оплатить?',
                'answer' => 'Картами Uzcard, Humo, Visa и Mastercard через интернет-эквайринг Uzum Bank, в сумах. Платёж подтверждается кодом 3-D Secure. Подробнее — на странице «Способы оплаты».',
            ],
            'uz' => [
                'question' => 'Qaysi kartalar bilan to‘lash mumkin?',
                'answer' => 'Uzcard, Humo, Visa va Mastercard kartalari bilan Uzum Bank internet-ekvayringi orqali, so‘mda. To‘lov 3-D Secure kodi bilan tasdiqlanadi. Batafsil — «To‘lov usullari» sahifasida.',
            ],
            'en' => [
                'question' => 'Which cards can I pay with?',
                'answer' => 'Uzcard, Humo, Visa and Mastercard through Uzum Bank online acquiring, in soum. The payment is confirmed by a 3-D Secure code. Details are on the “Payment methods” page.',
            ],
            'zh' => [
                'question' => '可以用哪些银行卡支付？',
                'answer' => '可使用 Uzcard、Humo、Visa 和 Mastercard，通过 Uzum Bank 网络收单以苏姆支付。付款需经 3-D Secure 验证码确认。详见「支付方式」页面。',
            ],
            'tr' => [
                'question' => 'Hangi kartlarla ödeme yapılabilir?',
                'answer' => 'Uzcard, Humo, Visa ve Mastercard ile Uzum Bank internet sanal POS üzerinden, som cinsinden. Ödeme 3-D Secure koduyla onaylanır. Ayrıntılar «Ödeme yöntemleri» sayfasında.',
            ],
        ],
    ],
];
