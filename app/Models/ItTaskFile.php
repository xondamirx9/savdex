<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Файл техзадания к IT-задаче: лежит на приватном диске, скачивается
 * только вошедшими пользователями — ТЗ не должно индексироваться и
 * утекать по прямой ссылке.
 */
#[Fillable(['it_task_id', 'title', 'file_path', 'file_size', 'mime'])]
class ItTaskFile extends Model
{
    public const ALLOWED_MIMES = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'jpg', 'jpeg', 'png', 'zip'];

    public const MAX_SIZE_KB = 20480;

    public const MAX_FILES = 5;

    public function task(): BelongsTo
    {
        return $this->belongsTo(ItTask::class, 'it_task_id');
    }

    public function sizeLabel(): string
    {
        $kb = $this->file_size / 1024;

        return $kb >= 1024
            ? number_format($kb / 1024, 1, ',', ' ').' МБ'
            : number_format(max(1, $kb), 0, ',', ' ').' КБ';
    }

    public function extension(): string
    {
        return strtolower(pathinfo($this->title, PATHINFO_EXTENSION) ?: pathinfo($this->file_path, PATHINFO_EXTENSION));
    }
}
