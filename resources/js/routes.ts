/**
 * Пути приложения.
 *
 * Без Ziggy: тот тянет в бандл весь список маршрутов Laravel вместе
 * с админскими. Здесь адреса типизированы, и опечатка ловится компилятором.
 * При изменении routes/web.php поправить и здесь.
 */
export const routes = {
    home: '/',

    // Публичная часть
    catalog: '/catalog',
    companies: '/companies',
    company: (slug: string) => `/company/${slug}`,
    listing: (slug: string) => `/listing/${slug}`,
    news: '/news',
    newsPost: (slug: string) => `/news/${slug}`,
    /* Список закупок — вкладка каталога; у самой закупки адрес свой */
    tenders: '/catalog?type=tender',
    tender: (slug: string) => `/tenders/${slug}`,
    itTasks: '/it-services',
    /* Страница направления «Доп. услуг»: it, hr, recruitment, logistics… */
    serviceSection: (slug: string) => `/services/${slug}`,
    resumes: '/resumes',
    resume: (slug: string) => `/resume/${slug}`,
    itTask: (slug: string) => `/it-services/${slug}`,
    itTaskRespond: (id: number) => `/it-services/${id}/respond`,
    itTaskFile: (id: number) => `/it-services/files/${id}`,
    terms: '/terms',
    payment: '/payment',
    security: '/security',
    privacy: '/privacy',
    refunds: '/refunds',
    about: '/about',
    help: '/help',
    guide: '/guide',
    rules: '/rules',
    pricing: '/pricing',
    countries: '/countries',
    partners: '/partners',
    partnersTier: (tier: 'general' | 'regular' | 'multi') => `/partners/${tier}`,
    reviews: '/reviews',
    reviewsNew: '/reviews/new',
    contacts: '/contact',

    // Избранное
    favorites: '/favorites',
    favoriteToggle: (id: number) => `/favorites/${id}`,

    // Вход
    login: '/login',
    /** Вход с возвратом на текущую страницу (гость нажал «В избранное», «Откликнуться») */
    loginBack: () =>
        typeof window === 'undefined'
            ? '/login'
            : `/login?back=${encodeURIComponent(window.location.pathname + window.location.search)}`,
    logout: '/logout',
    register: '/register',
    registerEmail: '/register/email',
    registerCode: '/register/code',
    registerCodeResend: '/register/code/resend',
    registerDetails: '/register/details',
    passwordRequest: '/forgot-password',
    passwordForced: '/password/change',
    verifyNotice: '/verify-email',
    verifyCode: '/verify-email/code',
    verifyResend: '/email/verification-notification',

    // Уведомления
    notifications: '/notifications',
    notificationRead: (id: number) => `/notifications/${id}/read`,
    notificationsReadAll: '/notifications/read-all',

    // Кабинет
    cabinet: '/cabinet',
    cabinetListings: '/cabinet/listings',
    cabinetResume: '/cabinet/resume',
    cabinetIncoming: '/cabinet/incoming',
    cabinetAnalytics: '/cabinet/analytics',
    cabinetPromo: '/cabinet/promo',
    cabinetCompany: '/cabinet/company',
    cabinetContacts: '/cabinet/contacts',
    cabinetChats: '/cabinet/chats',
    companyContacts: '/cabinet/company/contacts',
    companyContact: (id: number) => `/cabinet/company/contacts/${id}`,
    cabinetChat: (id: number) => `/cabinet/chats/${id}`,
    listingRespond: (id: number) => `/listing/${id}/respond`,
    cabinetBilling: '/cabinet/billing',
    cabinetReviews: '/cabinet/reviews',
    cabinetSettings: '/cabinet/settings',
    cabinetSite: '/cabinet/site',
    cabinetCards: '/cabinet/cards',
    cabinetCard: (id: number) => `/cabinet/cards/${id}`,
    cabinetSitePreview: '/cabinet/site/preview',
    cabinetSitePublish: '/cabinet/site/publish',
    cabinetSiteUnpublish: '/cabinet/site/unpublish',
    cabinetSiteHero: '/cabinet/site/hero',
    cabinetSiteProducts: '/cabinet/site/products',
    cabinetSiteProduct: (id: number) => `/cabinet/site/products/${id}`,
    listingCreate: '/cabinet/listings/create',
    cabinetItTasks: '/cabinet/it-tasks',
    itTaskCreate: '/cabinet/it-tasks/create',
    itTaskEdit: (id: number) => `/cabinet/it-tasks/${id}/edit`,
    itTaskUpdate: (id: number) => `/cabinet/it-tasks/${id}`,
    itTaskClose: (id: number) => `/cabinet/it-tasks/${id}/close`,
    itTaskReopen: (id: number) => `/cabinet/it-tasks/${id}/reopen`,
    itTaskComplete: (id: number) => `/cabinet/it-tasks/${id}/complete`,
    itTaskFileDelete: (id: number, fileId: number) => `/cabinet/it-tasks/${id}/files/${fileId}`,
    listingEdit: (id: number) => `/cabinet/listings/${id}/edit`,
} as const;
