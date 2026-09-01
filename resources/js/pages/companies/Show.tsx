import { useForm, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    Building2, CheckCircle2, Copy, Download, ExternalLink, FileText, Files, Globe, Layers,
    Lock, LockOpen, Mail, MapPin, Phone, QrCode, Send, Shield, Star, Users,
} from 'lucide-react';
import { useState } from 'react';
import { CompanyReviews, type CompanyReview } from '@/components/CompanyReviews';
import { Modal } from '@/components/Modal';
import { QrModal } from '@/components/QrModal';
import { Button } from '@/components/ui';
import { PublicLayout } from '@/layouts/PublicLayout';
import { renderRichText } from '@/lib/richtext';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

interface Contact {
    type: string;
    label: string | null;
    contact_person: string | null;
    value: string;
    href: string | null;
    /** Скрыт до оплаты. Сайт компании не скрывается никогда. */
    locked: boolean;
}

/** «1 контакт», «2 контакта», «5 контактов» */
function plural(n: number, one: string, few: string, many: string): string {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
}

interface BusinessCard {
    slug: string;
    name: string;
    legal_name: string | null;
    tin: string | null;
    type: string | null;
    type_label: string | null;
    custom_category: string | null;
    country: string | null;
    city: string | null;
    address: string | null;
    description: string | null;
    founded_year: number | null;
    employees_range: string | null;
    verification_level: number;
    rating: number;
    reviews_count: number;
    logo: string | null;
    cover: string | null;
    /** Пометка «данные из открытых источников»; null — блок скрыт */
    source_note: string | null;
    website: string | null;
    url: string;
}

const CONTACT_ICONS: Record<string, typeof Phone> = {
    phone: Phone,
    email: Mail,
    telegram: Send,
    whatsapp: Send,
    website: Globe,
};

/** Строка реквизита визитки. */
function Fact({ icon: Icon, label, children }: { icon: typeof Phone; label: string; children: React.ReactNode }) {
    return (
        <div className="fact">
            <dt>
                <Icon aria-hidden className="size-4" /> {label}
            </dt>
            <dd>{children}</dd>
        </div>
    );
}

interface CompanyFile {
    is_image: boolean;
    id: number;
    title: string;
    type: string;
    type_label: string;
    size: string | null;
    is_material: boolean;
    expired: boolean;
    valid_until: string | null;
}

export default function CompanyShow({
    company,
    initials,
    contacts,
    files,
    locked_count: lockedCount,
    unlocked,
    is_own: isOwn,
    wallet,
    reviews,
    review_blocked: reviewBlocked,
    criteria,
    listings_count: listingsCount,
}: {
    company: BusinessCard;
    initials: string;
    contacts: Contact[];
    /** Файлы, которые компания решила показать партнёрам */
    files: CompanyFile[];
    reviews: CompanyReview[];
    /** Причина, по которой отзыв оставить нельзя. null — можно */
    review_blocked: string | null;
    /** Критерии оценки: ключ поля => подпись */
    criteria: Record<string, string>;
    listings_count: number;
    /** Сколько контактов реально скрыто. Сайт компании сюда не входит. */
    locked_count: number;
    /** Контакты открыты: своя компания либо кредит уже списан */
    unlocked: boolean;
    is_own: boolean;
    /** Остаток покупателя. null для гостя и для своей же визитки */
    wallet: { contacts_left: number; credits: number } | null;
}) {
    const { auth } = usePage<SharedProps>().props;
    const [qrOpen, setQrOpen] = useState(false);
    const [unlockOpen, setUnlockOpen] = useState(false);
    const unlockForm = useForm({});

    // Хватит ли чего-нибудь на раскрытие: лимита тарифа либо кредитов
    const canUnlock = wallet !== null && (wallet.contacts_left > 0 || wallet.credits > 0);
    const [copied, setCopied] = useState(false);

    async function copyTin() {
        if (!company.tin) return;
        try {
            await navigator.clipboard.writeText(company.tin);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // Clipboard API недоступен по http — молча ничего не делаем,
            // ИНН и так виден и его можно выделить мышью
        }
    }

    return (
        <PublicLayout
            title={company.name}
            description={`${company.name}${company.city ? `, ${company.city}` : ''}. ${company.description ?? ''}`.slice(0, 160)}
        >
            <div className="container" style={{ paddingBottom: 96 }}>
                <nav aria-label="Хлебные крошки" style={{ padding: '20px 0 16px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li><Link href={routes.home}>Главная</Link></li>
                        <li aria-hidden="true">/</li>
                        <li><Link href={routes.companies}>Компании</Link></li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>{company.name}</li>
                    </ol>
                </nav>

                {/* ═══ ВИЗИТКА ═══ */}
                <div
                    className="cover"
                    style={
                        company.cover
                            ? {
                                  backgroundImage: `url(${company.cover})`,
                                  backgroundSize: 'cover',
                                  backgroundPosition: 'center',
                              }
                            : undefined
                    }
                />
                <div className="co-head">
                    <div className="row wrap" style={{ gap: 20, alignItems: 'flex-end' }}>
                        <div className="co-logo">{company.logo ? <img src={company.logo} alt="" /> : initials}</div>
                        <div style={{ flex: 1, minWidth: 240, paddingTop: 16 }}>
                            <div className="row wrap" style={{ gap: 10, marginBottom: 8 }}>
                                <h1 className="t-h1">{company.name}</h1>
                                {company.verification_level >= 3 ? (
                                    <span className="badge badge-gold"><Shield aria-hidden className="size-3.5" /> Проверена+</span>
                                ) : company.verification_level >= 2 ? (
                                    <span className="badge badge-verified"><CheckCircle2 aria-hidden className="size-3.5" /> Проверена</span>
                                ) : (
                                    <span className="badge badge-neutral">Не проверена</span>
                                )}
                            </div>
                            <p className="t-lead">
                                {[company.type_label, company.custom_category, company.city, company.country]
                                    .filter(Boolean)
                                    .join(' · ')}
                            </p>
                        </div>
                        <div className="row" style={{ gap: 10, paddingTop: 16 }}>
                            {/* Раньше здесь была кнопка-иконка QR. Иконка не объясняла,
                                что произойдёт, и мало кто её нажимал. Теперь понятная
                                надпись, а QR-код показывается внутри вместе со ссылкой. */}
                            {/* Кнопка сайта — всегда, когда сайт заполнен:
                                и для карточек площадки, и для своих */}
                            {company.website && (
                                <a
                                    href={company.website}
                                    target="_blank"
                                    rel="noopener nofollow"
                                    className="btn btn-secondary"
                                >
                                    <Globe aria-hidden className="size-4" /> Сайт компании
                                </a>
                            )}
                            <Button variant="secondary" onClick={() => setQrOpen(true)}>
                                <QrCode aria-hidden className="size-4" /> Сгенерировать ссылку
                            </Button>
                            {lockedCount > 0 &&
                                /* Кнопка ведёт туда, где действие реально доступно.
                                   Кнопка, которая ничего не делает, хуже её отсутствия:
                                   человек решает, что сайт сломан. */
                                (auth?.user ? (
                                    <Button onClick={() => setUnlockOpen(true)}>
                                        <Lock aria-hidden className="size-4" /> Показать контакты
                                    </Button>
                                ) : (
                                    <Link href={routes.register} className="btn btn-primary">
                                        <Lock aria-hidden className="size-4" /> Показать контакты
                                    </Link>
                                ))}

                            {/* Купленный доступ отмечается явно: иначе человек,
                                уже заплативший за компанию, каждый раз заново
                                гадает, спишется ли кредит при открытии карточки */}
                            {unlocked && !isOwn && (
                                <span className="badge badge-verified" style={{ height: 40, padding: '0 14px' }}>
                                    <LockOpen aria-hidden className="size-4" /> Контакты открыты
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Карточка заведена площадкой из открытых источников:
                        визитка говорит об этом честно, а кнопка ведёт на
                        сайт компании — подтверждение, что она настоящая.
                        Текст и сайт правятся в админке (Компании) */}
                    {company.source_note && (
                        <div className="alert alert-info mt-24" style={{ alignItems: 'center', gap: 14 }}>
                            <FileText aria-hidden className="size-5 shrink-0" />
                            {/* Кнопка сайта — в шапке визитки, здесь только текст */}
                            <div style={{ flex: 1, minWidth: 220 }} className="t-sm">
                                {company.source_note}
                            </div>
                        </div>
                    )}

                    <dl className="card-facts mt-24">
                        {company.legal_name && (
                            <Fact icon={Building2} label="Юридическое название">{company.legal_name}</Fact>
                        )}
                        <Fact icon={Files} label="ИНН / СТИР">
                            {company.tin ? (
                                <span className="row" style={{ gap: 6 }}>
                                    <b style={{ fontVariantNumeric: 'tabular-nums' }}>{company.tin}</b>
                                    <button
                                        className="btn btn-ghost btn-icon btn-sm"
                                        onClick={copyTin}
                                        aria-label={copied ? 'ИНН скопирован' : 'Скопировать ИНН'}
                                    >
                                        {copied ? <CheckCircle2 aria-hidden className="text-success size-4" /> : <Copy aria-hidden className="size-4" />}
                                    </button>
                                </span>
                            ) : (
                                <span className="muted">не указан</span>
                            )}
                        </Fact>
                        <Fact icon={Globe} label="Страна">{company.country ?? '—'}</Fact>
                        {company.address && <Fact icon={MapPin} label="Адрес">{company.address}</Fact>}
                        <Fact icon={Users} label="Сотрудников">
                            {company.employees_range ?? '—'}
                            {company.founded_year ? ` · основана в ${company.founded_year}` : ''}
                        </Fact>
                        <Fact icon={Layers} label="Тип компании">
                            {company.type_label ?? '—'}
                        </Fact>
                    </dl>

                    {company.description && (
                        <div className="t-body muted mt-24 prose rich">{renderRichText(company.description)}</div>
                    )}

                    {/* Контакты */}
                    <div className="contacts-strip mt-24">
                        <div className="row-between wrap" style={{ gap: 12, marginBottom: 14 }}>
                            <h2 className="t-h4">Контакты</h2>
                            {lockedCount === 0 ? (
                                <span className="badge badge-verified">
                                    <CheckCircle2 aria-hidden className="size-3.5" /> Контакты открыты
                                </span>
                            ) : (
                                <span className="badge badge-neutral">
                                    <Lock aria-hidden className="size-3.5" /> {lockedCount}{' '}
                                    {plural(lockedCount, 'контакт скрыт', 'контакта скрыто', 'контактов скрыто')}
                                </span>
                            )}
                        </div>

                        <div className="contacts-grid">
                            {contacts.map((c, i) => {
                                const Icon = CONTACT_ICONS[c.type] ?? Phone;
                                return (
                                    <div key={i} className={`contact-item ${c.locked ? 'is-locked' : 'is-open'}`}>
                                        <span className="ico-box ico-box-sm">
                                            <Icon aria-hidden className="size-4" />
                                        </span>
                                        <div>
                                            <div className="contact-value">
                                                {c.href ? <a href={c.href}>{c.value}</a> : c.value}
                                            </div>
                                            {(c.label || c.contact_person) && (
                                                <div className="contact-label">
                                                    {[c.label, c.contact_person].filter(Boolean).join(' · ')}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        {lockedCount > 0 && (
                            <p className="t-caption muted mt-16">
                                Домен почты и код оператора видны сразу — чтобы было понятно, что контакт настоящий.
                                Полные данные откроются после оплаты, один раз и навсегда по всей компании.
                            </p>
                        )}
                    </div>

                    {/* Фотографии компании: производство, склад, продукция.
                        Загружаются во вкладке «Файлы и материалы» кабинета —
                        картинки с публикацией попадают сюда галереей */}
                    {files.some((f) => f.is_image) && (
                        <div className="mt-24">
                            <h2 className="t-h4" style={{ marginBottom: 14 }}>
                                Фотографии
                            </h2>
                            <div className="co-photos">
                                {files.filter((f) => f.is_image).map((f) => (
                                    <a key={f.id} href={`/files/${f.id}`} target="_blank" rel="noopener" title={f.title}>
                                        <img src={`/files/${f.id}`} alt={f.title} loading="lazy" />
                                    </a>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Материалы компании: презентации, прайсы, документы.
                        Компания сама решает, что показывать — на визитке
                        только то, что помечено к публикации */}
                    {files.some((f) => !f.is_image) && (
                        <div className="mt-24">
                            <h2 className="t-h4" style={{ marginBottom: 14 }}>
                                Документы и материалы
                            </h2>
                            <div className="files-grid">
                                {files.filter((f) => !f.is_image).map((f) => (
                                    <a key={f.id} href={`/files/${f.id}`} className="file-card">
                                        <span className="ico-box ico-box-sm">
                                            <FileText aria-hidden className="size-4" />
                                        </span>
                                        <span style={{ minWidth: 0, flex: 1 }}>
                                            <span className="file-title">{f.title}</span>
                                            <span className="t-caption muted">
                                                {f.type_label}
                                                {f.size && ` · ${f.size}`}
                                                {f.valid_until && ` · до ${f.valid_until}`}
                                            </span>
                                        </span>
                                        {/* Просроченный документ не молчим: он не подтверждает
                                            ничего, и партнёр должен это видеть до звонка */}
                                        {f.expired && <span className="badge badge-danger">истёк</span>}
                                        <Download aria-hidden className="size-4 shrink-0 muted" />
                                    </a>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="grid grid-4 grid-tight mt-24" style={{ paddingTop: 20, borderTop: '1px solid var(--border)' }}>
                        <div>
                            <div className="t-num" style={{ fontSize: 24, lineHeight: '32px' }}>
                                {company.rating.toFixed(1)}
                            </div>
                            <div className="t-sm muted">
                                рейтинг · {company.reviews_count}{' '}
                                {plural(company.reviews_count, 'отзыв', 'отзыва', 'отзывов')}
                            </div>
                        </div>
                        <div>
                            <div className="t-num" style={{ fontSize: 24, lineHeight: '32px' }}>
                                <Star aria-hidden className="inline size-5" />
                            </div>
                            <div className="t-sm muted">отзывы — от открывших контакты</div>
                        </div>
                        <div>
                            <div className="t-num" style={{ fontSize: 24, lineHeight: '32px' }}>
                                {listingsCount}
                            </div>
                            <div className="t-sm muted">
                                {plural(listingsCount, 'активное объявление', 'активных объявления', 'активных объявлений')}
                            </div>
                        </div>
                        <div>
                            <a href={company.url} className="t-sm row" style={{ gap: 6 }}>
                                <ExternalLink aria-hidden className="size-4" /> Публичная ссылка
                            </a>
                        </div>
                    </div>
                </div>
            </div>

            <div className="container" style={{ paddingBottom: 48 }}>
                <CompanyReviews
                    slug={company.slug}
                    reviews={reviews}
                    blocked={reviewBlocked}
                    criteria={criteria}
                    rating={company.rating}
                />
            </div>

            <QrModal open={qrOpen} onClose={() => setQrOpen(false)} name={company.name} url={company.url} />

            {/*
                Раскрытие контактов. Стоимость и остаток показываются
                до нажатия: списание необратимо, и человек должен видеть,
                что именно спишется, прежде чем согласиться.
            */}
            <Modal
                open={unlockOpen}
                onClose={() => setUnlockOpen(false)}
                title="Открыть контакты компании"
                description={`${company.name} — ${plural(lockedCount, 'контакт', 'контакта', 'контактов')} скрыто`}
                width={460}
                footer={
                    <>
                        <button
                            className="btn btn-primary"
                            style={{ flex: 1 }}
                            disabled={unlockForm.processing || !canUnlock}
                            onClick={() =>
                                unlockForm.post(`/company/${company.slug}/unlock`, {
                                    preserveScroll: true,
                                    onSuccess: () => setUnlockOpen(false),
                                })
                            }
                        >
                            {unlockForm.processing ? 'Открываем…' : 'Открыть контакты'}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setUnlockOpen(false)}>
                            Отмена
                        </button>
                    </>
                }
            >
                <div className="card card--pad-sm" style={{ background: 'var(--bg)', border: 'none' }}>
                    <div className="row-between t-sm" style={{ marginBottom: 8 }}>
                        <span className="muted">Спишется</span>
                        <b>{wallet && wallet.contacts_left > 0 ? '1 контакт по тарифу' : '1 кредит'}</b>
                    </div>
                    {wallet && (
                        <div className="row-between t-sm">
                            <span className="muted">Останется</span>
                            <b>
                                {wallet.contacts_left > 0
                                    ? `${wallet.contacts_left - 1} по тарифу`
                                    : `${Math.max(0, wallet.credits - 1)} кредитов`}
                            </b>
                        </div>
                    )}
                </div>

                <p className="t-sm mt-16">
                    Контакты открываются <b>за компанию целиком</b> — один раз и навсегда, по всем её
                    объявлениям. Платить второй раз за эту компанию не придётся.
                </p>

                {/* Отказ объясняется до нажатия, а не после: кнопка,
                    которая отвечает ошибкой, читается как поломка */}
                {!canUnlock && (
                    <div className="alert alert-warning mt-16">
                        <Lock aria-hidden className="size-5" />
                        <div>
                            {wallet
                                ? 'Лимит контактов по тарифу исчерпан, кредитов нет. Купите пакет или смените тариф.'
                                : 'Сначала заполните данные компании — раскрытие идёт от её имени.'}
                        </div>
                    </div>
                )}
            </Modal>

        </PublicLayout>
    );
}
