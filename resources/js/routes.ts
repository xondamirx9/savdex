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
    tenders: '/tenders',
    tender: (slug: string) => `/tenders/${slug}`,
    itTasks: '/it-services',
    itTask: (slug: string) => `/it-services/${slug}`,
    itTaskRespond: (id: number) => `/it-services/${id}/respond`,
    itTaskFile: (id: number) => `/it-services/files/${id}`,
    terms: '/terms',
    payment: '/payment',
    security: '/security',
    privacy: '/privacy',
    refunds: '/refunds',
    about: '/about',
    pricing: '/pricing',
    countries: '/countries',
    partners: '/partners',
    contacts: '/contact',

    // Избранное
    favorites: '/favorites',
    favoriteToggle: (id: number) => `/favorites/${id}`,

    // Вход
    login: '/login',
    logout: '/logout',
    register: '/register',
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
    listingCreate: '/cabinet/listings/create',
    cabinetItTasks: '/cabinet/it-tasks',
    itTaskCreate: '/cabinet/it-tasks/create',
    itTaskEdit: (id: number) => `/cabinet/it-tasks/${id}/edit`,
    itTaskUpdate: (id: number) => `/cabinet/it-tasks/${id}`,
    itTaskClose: (id: number) => `/cabinet/it-tasks/${id}/close`,
    itTaskReopen: (id: number) => `/cabinet/it-tasks/${id}/reopen`,
    itTaskFileDelete: (id: number, fileId: number) => `/cabinet/it-tasks/${id}/files/${fileId}`,
    listingEdit: (id: number) => `/cabinet/listings/${id}/edit`,
} as const;
