<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class CityTranslation extends Model
{
    protected $fillable = ['city_id', 'locale', 'name'];
}
