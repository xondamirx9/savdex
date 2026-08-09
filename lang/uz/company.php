<?php

declare(strict_types=1);

return [
    'field' => [
        'name' => 'kompaniya nomi',
        'type' => 'kompaniya turi',
        'city' => 'shahar',
        'phone' => 'telefon',
        'email' => 'elektron pochta',
        'tin' => 'INN yoki STIR',
        'address' => 'yuridik manzil',
        'description' => 'kompaniya tavsifi (100 belgidan boshlab)',
        'logo' => 'logotip',
        'documents' => 'tasdiqlangan hujjatlar',
    ],

    'verification' => [
        0 => 'Tekshirilmagan',
        1 => 'Aloqalar tasdiqlangan',
        2 => 'Tekshirilgan',
        3 => 'Kengaytirilgan tekshiruv',
    ],

    'status' => [
        'active' => 'Faol',
        'pending' => 'Tekshiruvda',
        'blocked' => 'Bloklangan',
    ],

    'role' => [
        'supplier' => 'Yetkazib beruvchi',
        'buyer' => 'Xaridor',
        'both' => 'Yetkazib beruvchi va xaridor',
    ],
];
