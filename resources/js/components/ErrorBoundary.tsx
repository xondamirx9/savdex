import { router } from '@inertiajs/react';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';

/**
 * Защита от ошибок отрисовки.
 *
 * Ошибка в любом компоненте страницы раньше роняла всё дерево React —
 * белый экран без шапки и без выхода. Теперь вместо страницы — короткое
 * объяснение и две кнопки: обновить или на главную. Переход на другую
 * страницу (Inertia) снимает экран ошибки сам.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
    state = { failed: false };

    private stopListening: (() => void) | null = null;

    static getDerivedStateFromError(): { failed: boolean } {
        return { failed: true };
    }

    componentDidMount(): void {
        this.stopListening = router.on('navigate', () => {
            if (this.state.failed) this.setState({ failed: false });
        });
    }

    componentWillUnmount(): void {
        this.stopListening?.();
    }

    componentDidCatch(error: Error, info: ErrorInfo): void {
        // В консоль — для разбора: на экране человеку подробности ни к чему
        console.error('Ошибка отрисовки страницы', error, info.componentStack);
    }

    render(): ReactNode {
        if (!this.state.failed) return this.props.children;

        return (
            <main className="container" role="alert" style={{ padding: '96px 16px', textAlign: 'center' }}>
                <h1 className="t-h2">{label('errors.crash_title', 'Что-то пошло не так')}</h1>
                <p className="t-sm muted" style={{ maxWidth: 460, margin: '12px auto 24px' }}>
                    {label('errors.crash_text', 'Страница не смогла открыться. Обновите её или вернитесь на главную.')}
                </p>
                <div className="row" style={{ gap: 12, justifyContent: 'center' }}>
                    <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
                        {label('errors.crash_reload', 'Обновить страницу')}
                    </button>
                    <a className="btn btn-secondary" href={localize('/')}>
                        {label('errors.crash_home', 'На главную')}
                    </a>
                </div>
            </main>
        );
    }
}

/** Перевод, а если словаря нет (ошибка до его загрузки) — русский текст */
function label(key: string, fallback: string): string {
    const text = t(key);

    return text === key ? fallback : text;
}
