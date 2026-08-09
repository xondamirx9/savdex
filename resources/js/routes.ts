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
    terms: '/terms',
    privacy: '/privacy',
    refunds: '/refunds',
    about: '/about',
    pricing: '/pricing',
    countries: '/countries',
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
    cabinetBilling: '/cabinet/billing',
    cabinetReviews: '/cabinet/reviews',
    cabinetSettings: '/cabinet/settings',
    listingCreate: '/cabinet/listings/create',
    listingEdit: (id: number) => `/cabinet/listings/${id}/edit`,
} as const;
