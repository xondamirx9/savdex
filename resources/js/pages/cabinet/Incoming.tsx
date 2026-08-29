import { Link } from '@/components/ui/Link';
import { BadgeCheck, Eye, Lock, PhoneCall } from 'lucide-react';
import type { ReactNode } from 'react';
import { Empty } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { pluralize } from '@/lib/plural';

interface Row {
    id: number;
    name: string | null;
    slug: string | null;
    initials: string | null;
    verified: number;
    type: string;
    rating: number;
    city: string;
    listing: string | null;
    when: string;
}

interface ViewerRow {
    id: number;
    name: string | null;
    slug: string | null;
    initials: string | null;
    verified: number;
    type: string;
    rating: number;
    city: string;
    looked: string;
    views: number;
    when: string;
}

/** Ячейка «Компания»: имя за тарифным замком, тип и рейтинг всегда. */
function CompanyCell({
    row,
    seesNames,
}: {
    row: { name: string | null; slug: string | null; initials: string | null; verified: number; type: string; rating: number };
    seesNames: boolean;
}) {
    return (
        <div className="row" style={{ gap: 10 }}>
            <span className="listing-logo logo-32">
                {seesNames ? row.initials : <Lock aria-hidden className="size-3.5" />}
            </span>
            <span style={{ minWidth: 0 }}>
                {seesNames ? (
                    <>
                        <b>{row.slug ? <Link href={routes.company(row.slug)}>{row.name}</Link> : (row.name ?? 'Компания удалена')}</b>
                        {row.verified > 0 && (
                            <>
                                {' '}
                                <span className="badge badge-verified">
                                    <BadgeCheck aria-hidden className="size-3.5" />
                                </span>
                            </>
                        )}
                    </>
                ) : (
                    <b className="muted">Название скрыто</b>
                )}
                <br />
                <span className="t-caption muted">
                    {row.type}
                    {row.rating > 0 && ` · рейтинг ${row.rating.toFixed(1)}`}
                </span>
            </span>
        </div>
    );
}

function Section({ icon: Icon, title, hint, children }: { icon: typeof Eye; title: string; hint: string; children: ReactNode }) {
    return (
        <section className="card mt-24">
            <div className="row" style={{ gap: 10, marginBottom: 6 }}>
                <span className="ico-box ico-box-sm shrink-0">
                    <Icon aria-hidden className="size-4" />
                </span>
                <div>
                    <h2 className="t-h3">{title}</h2>
                    <p className="t-caption muted">{hint}</p>
                </div>
            </div>
            {children}
        </section>
    );
}

export default function Incoming({
    rows,
    viewers,
    sees_names,
    plan,
}: {
    rows: Row[];
    viewers: ViewerRow[];
    sees_names: boolean;
    plan: { name: string } | null;
}) {
    return (
        <CabinetLayout
            title="Кто мной интересуется"
            heading="Кто мной интересуется"
            subheading="Компании, которые открыли ваши контакты или смотрели ваши страницы за последние 30 дней"
        >
            {rows.length === 0 && viewers.length === 0 ? (
                <Empty
                    icon={Eye}
                    title="Пока никто не проявлял интереса"
                    text="Здесь появятся компании, которые смотрели ваши объявления и визитку или открыли ваши контакты. Чем полнее карточка и активнее объявления, тем быстрее это случится."
                    action={{ href: routes.cabinetListings, label: 'Проверить объявления' }}
                />
            ) : (
                <>
                    {rows.length > 0 && (
                        <Section
                            icon={PhoneCall}
                            title="Открыли ваши контакты"
                            hint="Самые тёплые лиды: они заплатили за ваш контакт и готовы к разговору"
                        >
                            <div className="table-wrap table-cards">
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>Компания</th>
                                            <th>Объявление</th>
                                            <th>Когда</th>
                                            <th>Город</th>
                                            <th>
                                                <span className="sr-only">Действия</span>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.map((row) => (
                                            <tr key={row.id}>
                                                <td data-label="Компания">
                                                    <CompanyCell row={row} seesNames={sees_names} />
                                                </td>
                                                <td data-label="Объявление">
                                                    <span className="t-sm">{row.listing ?? '—'}</span>
                                                </td>
                                                <td data-label="Когда">{row.when}</td>
                                                <td data-label="Город">{row.city}</td>
                                                <td data-label="">
                                                    {sees_names && row.slug ? (
                                                        <Link href={routes.company(row.slug)} className="btn btn-secondary btn-sm">
                                                            Написать первым
                                                        </Link>
                                                    ) : (
                                                        <span className="t-caption muted">—</span>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Section>
                    )}

                    {viewers.length > 0 && (
                        <Section
                            icon={Eye}
                            title="Смотрели вас"
                            hint="Компании, открывавшие ваши объявления и визитку — интерес, который ещё можно превратить в сделку"
                        >
                            <div className="table-wrap table-cards">
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>Компания</th>
                                            <th>Что смотрели</th>
                                            <th>Просмотры</th>
                                            <th>Когда</th>
                                            <th>Город</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {viewers.map((v) => (
                                            <tr key={v.id}>
                                                <td data-label="Компания">
                                                    <CompanyCell row={v} seesNames={sees_names} />
                                                </td>
                                                <td data-label="Что смотрели">
                                                    <span className="t-sm">{v.looked || '—'}</span>
                                                </td>
                                                <td data-label="Просмотры">
                                                    {pluralize(v.views, ['просмотр', 'просмотра', 'просмотров'])}
                                                </td>
                                                <td data-label="Когда">{v.when}</td>
                                                <td data-label="Город">{v.city}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Section>
                    )}

                    {/* Ограничение объясняется прямо: непонятно скрытое название
                        раздражает, понятное — становится доводом за тариф */}
                    {!sees_names && (
                        <div className="card mt-24" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                            <div className="row-between wrap" style={{ gap: 16 }}>
                                <div style={{ flex: 1, minWidth: 260 }}>
                                    <b>Названия компаний видны на тарифах Business и Premium</b>
                                    <p className="t-sm muted mt-8">
                                        На тарифе {plan?.name} показываются город и тип компании. Сам факт интереса
                                        виден всегда.
                                    </p>
                                </div>
                                <Link href={routes.pricing} className="btn btn-primary">
                                    Сравнить тарифы
                                </Link>
                            </div>
                        </div>
                    )}
                </>
            )}
        </CabinetLayout>
    );
}
