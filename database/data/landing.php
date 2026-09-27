<?php

/*
 * Тексты главной страницы — такими, какими их показывал сайт, когда
 * они жили в словарях lang/<язык>/ui.php (раздел home). Их один раз
 * переносит в базу миграция 2026_09_28_180000_landing_from_dictionaries;
 * дальше тексты правят в админке, и этот файл — только история переноса.
 *
 * Порядок блоков — порядок секций в макете (resources/js/pages/Home.tsx).
 * У «Как это работает» и «Частых вопросов» пункты в тексте: название
 * первой строкой, пояснение следующей, пункты — через пустую строку.
 */
return [
    'hero' => [
        'name' => 'Первый экран',
        'texts' => [
            'ru' => [
                'heading' => 'Поставщики и закупщики находят друг друга',
                'subheading' => 'Разместите предложение или запрос бесплатно. Получите прямые контакты компаний — без посредников и без комиссии со сделок.',
            ],
            'uz' => [
                'heading' => 'Yetkazib beruvchilar va xaridorlar bir-birini topadi',
                'subheading' => 'Taklif yoki so‘rovni bepul joylashtiring. Kompaniyalarning to‘g‘ridan-to‘g‘ri kontaktlarini oling — vositachilarsiz va bitimdan komissiyasiz.',
            ],
            'en' => [
                'heading' => 'Where suppliers and buyers find each other',
                'subheading' => 'Post an offer or a request for free. Get direct company contacts — no middlemen, no commission on deals.',
            ],
            'zh' => [
                'heading' => '供应商与采购商在此相遇',
                'subheading' => '免费发布供应或求购信息，直接获取企业联系方式 —— 没有中间商，交易不收佣金。',
            ],
            'tr' => [
                'heading' => 'Tedarikçiler ve alıcılar burada buluşuyor',
                'subheading' => 'Teklifinizi veya talebinizi ücretsiz yayınlayın. Şirketlerin doğrudan iletişim bilgilerini alın — aracısız ve işlem komisyonu olmadan.',
            ],
        ],
    ],
    'stats' => [
        'name' => 'Счётчики',
        'texts' => [
            'ru' => [
            ],
            'uz' => [
            ],
            'en' => [
            ],
            'zh' => [
            ],
            'tr' => [
            ],
        ],
    ],
    'categories' => [
        'name' => 'Популярные категории',
        'texts' => [
            'ru' => [
                'heading' => 'Популярные категории',
            ],
            'uz' => [
                'heading' => 'Ommabop toifalar',
            ],
            'en' => [
                'heading' => 'Popular categories',
            ],
            'zh' => [
                'heading' => '热门类目',
            ],
            'tr' => [
                'heading' => 'Popüler kategoriler',
            ],
        ],
    ],
    'vip' => [
        'name' => 'VIP-предложения',
        'texts' => [
            'ru' => [
                'heading' => 'VIP-предложения',
            ],
            'uz' => [
                'heading' => 'VIP takliflar',
            ],
            'en' => [
                'heading' => 'VIP offers',
            ],
            'zh' => [
                'heading' => 'VIP 精选',
            ],
            'tr' => [
                'heading' => 'VIP teklifler',
            ],
        ],
    ],
    'requests' => [
        'name' => 'Запросы (RFQ)',
        'texts' => [
            'ru' => [
                'heading' => 'Запросы (RFQ)',
            ],
            'uz' => [
                'heading' => 'So‘rovlar (RFQ)',
            ],
            'en' => [
                'heading' => 'Requests (RFQ)',
            ],
            'zh' => [
                'heading' => '采购需求 (RFQ)',
            ],
            'tr' => [
                'heading' => 'Talepler (RFQ)',
            ],
        ],
    ],
    'suppliers' => [
        'name' => 'Поставщики',
        'texts' => [
            'ru' => [
                'heading' => 'Поставщики',
            ],
            'uz' => [
                'heading' => 'Yetkazib beruvchilar',
            ],
            'en' => [
                'heading' => 'Suppliers',
            ],
            'zh' => [
                'heading' => '供应商',
            ],
            'tr' => [
                'heading' => 'Tedarikçiler',
            ],
        ],
    ],
    'how' => [
        'name' => 'Как это работает',
        'texts' => [
            'ru' => [
                'eyebrow' => 'Как это работает',
                'heading' => 'Четыре шага до прямого разговора',
                'subheading' => 'От регистрации до сделки — без посредников и согласований.',
                'body' => 'Зарегистрируйтесь
Почта, пароль, данные компании. Две минуты, карта не нужна.

Разместите товар
Категория, объём, цена, условия поставки, фото и сертификаты.

Получайте входящие
Видно, кто открыл ваши контакты, из какого города и по какому объявлению.

Договоритесь напрямую
Созвон, договор, оплата — всё между вами. Площадка не вмешивается.',
            ],
            'uz' => [
                'eyebrow' => 'Bu qanday ishlaydi',
                'heading' => 'To‘g‘ridan-to‘g‘ri suhbatgacha to‘rt qadam',
                'subheading' => 'Ro‘yxatdan o‘tishdan bitimgacha — vositachilarsiz va kelishuvlarsiz.',
                'body' => 'Ro‘yxatdan o‘ting
Pochta, parol, kompaniya ma’lumotlari. Ikki daqiqa, karta kerak emas.

Mahsulotni joylashtiring
Toifa, hajm, narx, yetkazib berish shartlari, foto va sertifikatlar.

Kiruvchi so‘rovlarni oling
Kontaktlaringizni kim, qaysi shahardan va qaysi e’lon bo‘yicha ochgani ko‘rinadi.

To‘g‘ridan-to‘g‘ri kelishing
Qo‘ng‘iroq, shartnoma, to‘lov — barchasi o‘zingiz o‘rtangizda. Platforma aralashmaydi.',
            ],
            'en' => [
                'eyebrow' => 'How it works',
                'heading' => 'Four steps to a direct conversation',
                'subheading' => 'From sign-up to the deal — no middlemen, no approvals.',
                'body' => 'Sign up
Email, password, company details. Two minutes, no card required.

Post your goods
Category, volume, price, delivery terms, photos and certificates.

Receive enquiries
You see who unlocked your contacts, from which city and for which listing.

Agree directly
Calls, contracts, payments — all between you. The platform stays out of it.',
            ],
            'zh' => [
                'eyebrow' => '如何运作',
                'heading' => '四步直接对话',
                'subheading' => '从注册到成交 —— 没有中间商，无需层层审批。',
                'body' => '注册账号
邮箱、密码、企业资料。两分钟，无需银行卡。

发布货源
类目、数量、价格、供货条件、照片与证书。

接收询盘
可以看到谁解锁了您的联系方式、来自哪个城市、针对哪条信息。

直接洽谈
通话、合同、付款 —— 全在双方之间，平台不介入。',
            ],
            'tr' => [
                'eyebrow' => 'Nasıl çalışır',
                'heading' => 'Doğrudan görüşmeye dört adım',
                'subheading' => 'Kayıttan anlaşmaya — aracısız ve onay beklemeden.',
                'body' => 'Kayıt olun
E-posta, şifre, şirket bilgileri. İki dakika, kart gerekmez.

Ürününüzü yayınlayın
Kategori, miktar, fiyat, teslim koşulları, fotoğraf ve sertifikalar.

Talepleri alın
İletişim bilgilerinizi kimin, hangi şehirden ve hangi ilan için açtığı görünür.

Doğrudan anlaşın
Görüşme, sözleşme, ödeme — hepsi aranızda. Platform araya girmez.',
            ],
        ],
    ],
    'reviews' => [
        'name' => 'Отзывы',
        'texts' => [
            'ru' => [
                'heading' => 'Отзывы пользователей',
            ],
            'uz' => [
                'heading' => 'Foydalanuvchilar fikrlari',
            ],
            'en' => [
                'heading' => 'User reviews',
            ],
            'zh' => [
                'heading' => '用户评价',
            ],
            'tr' => [
                'heading' => 'Kullanıcı yorumları',
            ],
        ],
    ],
    'faq' => [
        'name' => 'Частые вопросы',
        'texts' => [
            'ru' => [
                'heading' => 'Частые вопросы',
                'body' => 'Сколько стоит размещение объявлений?
Размещение бесплатное. Платные тарифы расширяют лимиты — больше объявлений, контактов и продвижения, — но базовая работа на площадке не стоит ничего.

Берёте ли вы комиссию со сделок?
Нет. Сделка проходит напрямую между вами и партнёром: созвон, договор, оплата. Площадка в расчётах не участвует и процента не берёт.

Как проверяются компании?
Модерация сверяет учредительные документы и ИНН. Прошедшие проверку получают бейдж «Проверена», расширенная проверка — «Проверена+». Отзывы появляются только от компаний, открывших контакты через площадку, — накрутить их нельзя.

Как связаться с поставщиком?
Откройте визитку компании и нажмите «Открыть контакты». На бесплатном тарифе — 3 открытия контактов в месяц, на платных лимит выше. Открытый контакт остаётся у вас навсегда.

Кто может зарегистрироваться на площадке?
Компании и предприниматели Узбекистана и всего региона: производители, импортёры, дистрибьюторы, торговые компании и сервисы. Нужны только почта и данные компании.

На каких языках работает площадка?
Русский, узбекский, английский, турецкий и китайский. Язык переключается в шапке сайта, и ссылку на страницу можно отправить партнёру сразу на его языке.',
            ],
            'uz' => [
                'heading' => 'Ko‘p beriladigan savollar',
                'body' => 'E’lon joylashtirish qancha turadi?
Joylashtirish bepul. Pullik tariflar limitlarni kengaytiradi — ko‘proq e’lon, kontakt va ilgari surish, — ammo maydondagi asosiy ish hech qancha turmaydi.

Bitimlardan komissiya olasizmi?
Yo‘q. Bitim siz va hamkoringiz o‘rtasida to‘g‘ridan-to‘g‘ri o‘tadi: qo‘ng‘iroq, shartnoma, to‘lov. Maydon hisob-kitoblarda qatnashmaydi va foiz olmaydi.

Kompaniyalar qanday tekshiriladi?
Moderatsiya ta’sis hujjatlari va STIRni tekshiradi. Tekshiruvdan o‘tganlar «Tekshirilgan» belgisini oladi, kengaytirilgan tekshiruv — «Tekshirilgan+». Sharhlarni faqat platforma orqali kontaktlarni ochgan kompaniyalar qoldira oladi — reytingni sun’iy oshirib bo‘lmaydi.

Yetkazib beruvchi bilan qanday bog‘lansa bo‘ladi?
Kompaniya sahifasini oching va «Kontaktlarni ochish» tugmasini bosing. Bepul tarifda oyiga 3 ta ochish bor, pullik tariflarda ko‘proq. Ochilgan kontakt sizda abadiy qoladi.

Maydonda kim ro‘yxatdan o‘ta oladi?
O‘zbekiston va butun mintaqa kompaniyalari hamda tadbirkorlari: ishlab chiqaruvchilar, importchilar, distribyutorlar, savdo kompaniyalari va xizmatlar. Faqat pochta va kompaniya ma’lumotlari kerak.

Maydon qaysi tillarda ishlaydi?
Rus, o‘zbek, ingliz, turk va xitoy tillarida. Til sayt sarlavhasida almashtiriladi, sahifa havolasini hamkorga o‘z tilida yuborish mumkin.',
            ],
            'en' => [
                'heading' => 'Frequently asked questions',
                'body' => 'How much does posting cost?
Posting is free. Paid plans extend the limits — more listings, contacts and promotion — but basic work on the platform costs nothing.

Do you take a commission on deals?
No. The deal happens directly between you and your partner: call, contract, payment. The platform is not involved in settlements and takes no percentage.

How are companies verified?
Moderators verify incorporation documents and the TIN. Verified companies get the “Verified” badge; extended checks earn “Verified+”. Reviews can only be left by companies that unlocked contacts through the platform, so ratings cannot be faked.

How do I contact a supplier?
Open a company profile and click “Unlock contacts”. The free plan includes 3 contact unlocks per month; paid plans include more. An unlocked contact stays with you forever.

Who can register on the platform?
Companies and entrepreneurs from Uzbekistan and the whole region: manufacturers, importers, distributors, trading companies and services. You only need an email and company details.

Which languages does the platform support?
Russian, Uzbek, English, Turkish and Chinese. Switch the language in the site header and share page links with partners in their own language.',
            ],
            'zh' => [
                'heading' => '常见问题',
                'body' => '发布信息需要多少费用？
发布免费。付费套餐扩大限额——更多信息、联系方式和推广——但平台的基本使用不收任何费用。

你们从交易中抽取佣金吗？
不。交易在您与伙伴之间直接进行：通话、合同、付款。平台不参与结算，也不抽取任何比例。

公司是如何审核的？
审核人员核对公司注册文件和税号。通过审核的企业获得“已认证”标识，扩展审核获得“已认证+”。只有通过平台解锁联系方式的企业才能留下评价，评分无法造假。

如何联系供应商？
打开企业名片并点击“解锁联系方式”。免费套餐每月含 3 次解锁，付费套餐更多。解锁的联系方式永久保留。

谁可以在平台注册？
乌兹别克斯坦及整个地区的公司和企业家：制造商、进口商、经销商、贸易公司和服务商。只需邮箱和公司信息。

平台支持哪些语言？
俄语、乌兹别克语、英语、土耳其语和中文。语言可在网站顶部切换，页面链接可直接以伙伴的语言发送给对方。',
            ],
            'tr' => [
                'heading' => 'Sık sorulan sorular',
                'body' => 'İlan yayınlamak ne kadar?
Yayınlamak ücretsizdir. Ücretli paketler limitleri genişletir — daha fazla ilan, iletişim ve tanıtım — ancak platformdaki temel çalışma hiçbir şey tutmaz.

Anlaşmalardan komisyon alıyor musunuz?
Hayır. Anlaşma sizinle ortağınız arasında doğrudan yapılır: görüşme, sözleşme, ödeme. Platform hesaplaşmalara karışmaz ve yüzde almaz.

Şirketler nasıl doğrulanıyor?
Moderasyon kuruluş belgelerini ve vergi numarasını kontrol eder. Onaylananlar «Doğrulanmış» rozetini, genişletilmiş kontrol «Doğrulanmış+» rozetini alır. Yorumları yalnızca platform üzerinden iletişim bilgilerini açan şirketler bırakabilir — puan şişirilemez.

Tedarikçiyle nasıl iletişim kurarım?
Şirket sayfasını açın ve «İletişimi aç» düğmesine basın. Ücretsiz pakette ayda 3 açma hakkı vardır, ücretli paketlerde daha fazla. Açılan iletişim bilgisi sonsuza dek sizde kalır.

Platforma kimler kaydolabilir?
Özbekistan ve tüm bölgeden şirketler ve girişimciler: üreticiler, ithalatçılar, distribütörler, ticaret şirketleri ve hizmetler. Yalnızca e-posta ve şirket bilgileri gerekir.

Platform hangi dillerde çalışıyor?
Rusça, Özbekçe, İngilizce, Türkçe ve Çince. Dil, site üstbilgisinden değiştirilir; sayfa bağlantısını ortağınıza kendi dilinde gönderebilirsiniz.',
            ],
        ],
    ],
    'news' => [
        'name' => 'Новости',
        'texts' => [
            'ru' => [
                'eyebrow' => 'Блог',
                'heading' => 'Новости площадки',
            ],
            'uz' => [
                'eyebrow' => 'Blog',
                'heading' => 'Platforma yangiliklari',
            ],
            'en' => [
                'eyebrow' => 'Blog',
                'heading' => 'Platform news',
            ],
            'zh' => [
                'eyebrow' => '博客',
                'heading' => '平台动态',
            ],
            'tr' => [
                'eyebrow' => 'Blog',
                'heading' => 'Platform haberleri',
            ],
        ],
    ],
    'cta' => [
        'name' => 'Призыв в конце',
        'texts' => [
            'ru' => [
                'heading' => 'Разместите первое объявление бесплатно',
                'subheading' => 'Регистрация занимает две минуты. Карта не нужна.',
                'button' => 'Зарегистрироваться',
                'body' => 'Бесплатно · 4 объявления · 3 контакта в месяц · без привязки карты',
            ],
            'uz' => [
                'heading' => 'Birinchi e’loningizni bepul joylashtiring',
                'subheading' => 'Ro‘yxatdan o‘tish ikki daqiqa oladi. Karta kerak emas.',
                'button' => 'Ro‘yxatdan o‘tish',
                'body' => 'Bepul · 4 ta e’lon · oyiga 3 ta kontakt · kartani bog‘lamasdan',
            ],
            'en' => [
                'heading' => 'Post your first listing for free',
                'subheading' => 'Signing up takes two minutes. No card required.',
                'button' => 'Sign up',
                'body' => 'Free · 4 listings · 3 contacts a month · no card required',
            ],
            'zh' => [
                'heading' => '免费发布您的第一条信息',
                'subheading' => '注册只需两分钟，无需银行卡。',
                'button' => '注册',
                'body' => '免费 · 4 条信息 · 每月 3 个联系方式 · 无需绑卡',
            ],
            'tr' => [
                'heading' => 'İlk ilanınızı ücretsiz yayınlayın',
                'subheading' => 'Kayıt iki dakika sürer. Kart gerekmez.',
                'button' => 'Kayıt ol',
                'body' => 'Ücretsiz · 4 ilan · ayda 3 iletişim · kart bağlamadan',
            ],
        ],
    ],
];
