import { PublicLayout } from '@/layouts/PublicLayout';

export default function ListingCreate() {
    return (
        <PublicLayout title="Новое объявление">
            <div className="container" style={{ padding: '32px 0 96px' }}>
                <h1 className="t-h1">Новое объявление</h1>
                <div className="card mt-24">
                    <p className="muted">Форма публикации — спринт 2 по плану работ.</p>
                </div>
            </div>
        </PublicLayout>
    );
}
