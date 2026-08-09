import { Head } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Check } from 'lucide-react';
import type { ReactNode } from 'react';
import { Logo } from '@/components/ui';

const BENEFITS = [
    'Размещение объявлений бесплатно, карта не нужна',
    '4 активных объявления и 3 контакта в месяц на старте',
    'Комиссии со сделок нет — договариваетесь напрямую',
    'Открытый контакт компании остаётся у вас навсегда',
];

/**
 * Раскладка экранов входа и регистрации.
 * Левая панель с аргументами скрывается ниже 1024 px: на телефоне
 * она отодвигает форму за экран и мешает, а не помогает.
 */
export function AuthLayout({
    title,
    heading,
    subheading,
    children,
}: {
    title: string;
    heading: string;
    subheading?: string;
    children: ReactNode;
}) {
    return (
        <>
            <Head title={title} />
            <a href="#form" className="skip-link">
                Перейти к форме
            </a>

            <div className="grid min-h-screen lg:grid-cols-[1fr_460px]">
                <aside className="bg-primary-700 hidden flex-col p-14 text-white lg:flex">
                    <Link href="/" aria-label="На главную">
                        <Logo inverted />
                    </Link>

                    <div className="my-auto">
                        {/* Не заголовок, а маркетинговый текст: структурный h1
                            страницы — это «Создайте аккаунт» в форме справа.
                            Заголовочный тег здесь давал в DOM h2 раньше h1
                            и ломал навигацию по заголовкам в скринридере.

                            Числа тоже нет намеренно: захардкоженное «1 240 компаний»
                            разойдётся с базой в первый же день. */}
                        <p className="text-h1 mb-5 leading-tight font-bold text-white">
                            Две минуты — и вы находите
                            <br />
                            поставщика напрямую
                        </p>
                        <ul className="space-y-1">
                            {BENEFITS.map((text) => (
                                <li key={text} className="flex items-start gap-3 py-3 text-[15px] text-white/90">
                                    <Check aria-hidden className="mt-0.5 size-5 shrink-0" />
                                    {text}
                                </li>
                            ))}
                        </ul>
                    </div>

                    <p className="text-sm text-white/65">© 2026 SAVDEX · ООО «ANJIR-GROUP», Узбекистан</p>
                </aside>

                <main
                    id="form"
                    className="bg-surface flex flex-col justify-center overflow-y-auto px-5 py-8 sm:px-10 lg:px-10 lg:py-12"
                >
                    <div className="mx-auto w-full max-w-[380px]">
                        <Link href="/" className="mb-7 inline-block lg:hidden" aria-label="На главную">
                            <Logo />
                        </Link>

                        <h1 className="text-h2 font-bold">{heading}</h1>
                        {subheading && <p className="text-muted mt-2 text-sm">{subheading}</p>}

                        <div className="mt-6">{children}</div>
                    </div>
                </main>
            </div>
        </>
    );
}
