import { Link } from '@/components/ui/Link';
import { BadgeCheck, Eye, Lock } from 'lucide-react';
import { Empty } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

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

export default function Incoming({
    rows,
    sees_names,
    plan,
}: {
    rows: Row[];
    sees_names: boolean;
    plan: { name: string } | null;
}) {
    return (
        <CabinetLayout
            title="Кто мной интересуется"
            heading="Кто мной интересуется"
            subheading="Компании, открывшие ваши контакты за последние 30 дней"
        >
            {rows.length === 0 ? (
                <Empty
                    icon={Eye}
                    title="Пока никто не открывал ваши контакты"
                    text="Здесь появятся компании, которые заплатили за ваш контакт — это самые тёплые лиды: они уже заинтересованы и готовы к разговору."
                    action={{ href: routes.cabinetListings, label: 'Проверить объявления' }}
                />
            ) : (
                <>
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
                                            <div className="row" style={{ gap: 10 }}>
                                                <span className="listing-logo logo-32">
                                                    {sees_names ? row.initials : <Lock aria-hidden className="size-3.5" />}
                                                </span>
                                                <span style={{ minWidth: 0 }}>
                                                    {sees_names ? (
                                                        <>
                                                            <b>
                                                                {row.slug ? (
                                                                    <Link href={routes.company(row.slug)}>{row.name}</Link>
                                                                ) : (
                                                                    row.name
                                                                )}
                                                            </b>
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
