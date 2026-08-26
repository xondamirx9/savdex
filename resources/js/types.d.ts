import type { PageProps as InertiaPageProps } from '@inertiajs/core';

export interface AuthUser {
    id: number;
    name: string;
    email: string;
    locale: string;
    email_verified: boolean;
    must_change_password: boolean;
    is_admin: boolean;
}

export interface AuthCompany {
    /** Логотип для шапки; null — показываются инициалы */
    logo: string | null;
    initials: string;
    id: number;
    name: string;
    slug: string;
    verification_level: number;
    profile_completeness: number;
}

/** Счётчики рядом с пунктами меню кабинета. */
export interface CabinetCounts {
    listings: number;
    contacts: number;
    incoming: number;
    reviews: number;
    /** Разговоры с непрочитанными сообщениями */
    chats: number;
}

export interface NotificationItem {
    id: number;
    type: string;
    tone: 'info' | 'success' | 'warning' | 'danger';
    title: string;
    read: boolean;
    ago: string;
}

/**
 * Остаток на раскрытие контактов.
 *
 * plan_left и total равны null у безлимитного тарифа — это «без
 * ограничений», а не ноль.
 */
export interface WalletSummary {
    plan_left: number | null;
    credits: number;
    total: number | null;
    resets_at: string | null;
}

/**
 * Контакты поддержки и реквизиты оператора из настроек админки.
 * Пустая строка — настройка не заполнена: блок с ней не показывается.
 */
export interface SupportContacts {
    email: string;
    phone: string;
    hours: string;
    /** Полная ссылка вида https://t.me/savdex. */
    telegram: string;
    legal_name: string;
    legal_tin: string;
}

export interface SharedProps extends InertiaPageProps {
    auth: { user: AuthUser | null; company: AuthCompany | null };
    flash: { success?: string; error?: string; warning?: string };
    counts?: CabinetCounts;
    /** Колокольчик в шапке. Не notifications: так называется проп страницы уведомлений. */
    bell?: { unread: number; latest: NotificationItem[] } | null;
    /**
     * Счётчик контактов в шапке. null у гостя и без компании.
     *
     * Не wallet: так называются пропсы страниц биллинга и визитки,
     * и они перекрыли бы общий.
     */
    contactsLeft?: WalletSummary | null;
    /**
     * Избранные объявления — только id: сердечку на карточке нужно
     * знать одно — закрашивать себя или нет. У гостя список пуст.
     */
    favorites?: number[];
    /** Разделы каталога для выпадающего списка поиска в шапке. */
    navCategories?: { id: number; name: string }[];
    /** Контакты поддержки и реквизиты — правятся в админке. */
    support: SupportContacts;
    locale: string;
    /** Адреса этой же страницы на других языках — для переключателя. */
    localeLinks: LocaleLink[];
    /** Язык по настройкам браузера, если он ещё не выбирался. */
    localeSuggest?: string | null;
    /**
     * Словарь интерфейса. Приходит только при полной загрузке
     * страницы — на переходах Inertia он у браузера уже есть.
     */
    translations?: Record<string, unknown> | null;
}

export interface LocaleLink {
    code: string;
    label: string;
    short: string;
    url: string;
}
