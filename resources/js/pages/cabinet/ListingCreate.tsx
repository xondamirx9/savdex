import { PublicLayout } from '@/layouts/PublicLayout';

export default function ListingCreate() {
    return (
        <PublicLayout title="Новое объявление">
            <div className="container" style={{ paddingBlock: '32px 96px' }}>
                <h1 className="t-h1">Новое объявление</h1>
                <div className="card mt-24">
                    <p className="muted">Форма публикации — спринт 2 по плану работ.</p>
                </div>
            </div>
        </PublicLayout>
    );
}
