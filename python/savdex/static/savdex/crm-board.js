/*
 * Доска лидов и сделок (templates/admin/crm/board.html).
 *
 * Перетаскивание — на событиях указателя, одинаково для мыши и пальца:
 * мышью карточка поднимается, как только её сдвинули; пальцем — после
 * долгого нажатия, чтобы обычный жест прокручивал доску, а не тащил
 * карточку. Отпустили над другой колонкой — открывается окно перевода
 * с полями этого этапа; если этапу спрашивать нечего — перевод сразу.
 *
 * Окно одно на страницу: поля этапа берутся из <template id="sx-fields-…">,
 * значения по умолчанию — из data-* карточки (ответственный, сумма).
 */
(function () {
  'use strict';

  var board = document.querySelector('.sx-board');
  if (!board) return;

  var columns = board.querySelector('.sx-board-columns');
  var moveDialog = document.getElementById('sx-move');
  var moveForm = document.getElementById('sx-move-form');
  var assignDialog = document.getElementById('sx-assign');
  var assignForm = document.getElementById('sx-assign-form');
  var current = null;

  // ── Окно перевода ──

  function setValue(form, name, value) {
    var field = form.elements[name];
    if (field && value !== undefined && value !== '') field.value = value;
  }

  function renderFields(card) {
    var box = moveForm.querySelector('[data-fields]');
    var template = document.getElementById('sx-fields-' + moveForm.elements.stage.value);
    box.innerHTML = '';
    if (template) box.appendChild(template.content.cloneNode(true));
    setValue(moveForm, 'owner', card.dataset.owner);
    setValue(moveForm, 'amount', card.dataset.amount);
    setValue(moveForm, 'currency', card.dataset.currency);
    setValue(moveForm, 'expected_close_at', card.dataset.expected);
  }

  function asksNothing() {
    var template = document.getElementById('sx-fields-' + moveForm.elements.stage.value);
    return !template || template.dataset.count === '0';
  }

  function openMove(card, stage, dropped) {
    if (!moveDialog) return;
    current = card;
    moveForm.action = card.dataset.moveUrl;
    moveForm.querySelector('[data-card-title]').textContent = card.dataset.title;

    var select = moveForm.elements.stage;
    var first = null;
    Array.prototype.forEach.call(select.options, function (option) {
      option.hidden = option.disabled = option.value === card.dataset.stage;
      if (!option.disabled && first === null) first = option.value;
    });
    select.value = stage || first;
    renderFields(card);

    // Перетащили на этап, которому спрашивать нечего, — переводим сразу
    if (dropped && asksNothing()) {
      moveForm.submit();
      return;
    }

    moveDialog.showModal();
    var focus = moveForm.querySelector('[data-fields] input, [data-fields] select, [data-fields] textarea');
    (focus || select).focus();
  }

  if (moveForm) {
    moveForm.elements.stage.addEventListener('change', function () {
      if (current) renderFields(current);
    });
  }

  function openAssign(card) {
    if (!assignDialog) return;
    assignForm.action = card.dataset.assignUrl;
    assignForm.querySelector('[data-card-title]').textContent = card.dataset.title;
    assignForm.elements.owner.value = card.dataset.owner || '';
    assignDialog.showModal();
  }

  [moveDialog, assignDialog].forEach(function (dialog) {
    if (!dialog) return;
    dialog.addEventListener('click', function (event) {
      // Щелчок мимо окна (по затемнению) или «Отмена» — закрыть
      if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
    });
  });

  board.addEventListener('click', function (event) {
    var card = event.target.closest('.sx-card');
    if (!card) return;
    if (event.target.closest('[data-move]')) openMove(card, null, false);
    if (event.target.closest('[data-assign]')) openAssign(card);
  });

  // ── Перетаскивание ──

  var LONG_PRESS = 350; // мс — палец держат, чтобы поднять карточку
  var drag = null;

  function cleanup() {
    if (!drag) return;
    clearTimeout(drag.timer);
    if (drag.ghost) drag.ghost.remove();
    if (drag.over) drag.over.classList.remove('is-over');
    drag.card.classList.remove('is-dragging', 'is-pressed');
    board.classList.remove('is-dragging');
    drag = null;
  }

  function place(x, y) {
    drag.ghost.style.transform = 'translate(' + (x - drag.offsetX) + 'px,' + (y - drag.offsetY) + 'px)';

    var under = document.elementFromPoint(x, y);
    var column = under && under.closest('.sx-col');
    var target = column && column.hasAttribute('data-droppable') &&
      column.dataset.stage !== drag.card.dataset.stage ? column : null;

    if (drag.over !== target) {
      if (drag.over) drag.over.classList.remove('is-over');
      if (target) target.classList.add('is-over');
      drag.over = target;
    }

    // У края доски — прокрутить колонки в ту сторону
    var box = columns.getBoundingClientRect();
    if (x < box.left + 48) columns.scrollLeft -= 14;
    else if (x > box.right - 48) columns.scrollLeft += 14;
  }

  function lift(x, y) {
    var box = drag.card.getBoundingClientRect();
    drag.active = true;
    drag.offsetX = x - box.left;
    drag.offsetY = y - box.top;
    drag.ghost = drag.card.cloneNode(true);
    drag.ghost.classList.add('sx-ghost');
    drag.ghost.removeAttribute('data-movable');
    drag.ghost.style.width = box.width + 'px';
    document.body.appendChild(drag.ghost);
    drag.card.classList.remove('is-pressed');
    drag.card.classList.add('is-dragging');
    board.classList.add('is-dragging');
    if (drag.touch && navigator.vibrate) navigator.vibrate(12);
    place(x, y);
  }

  board.addEventListener('pointerdown', function (event) {
    var card = event.target.closest('.sx-card[data-movable]');
    if (!card || event.button !== 0 || drag) return;
    // Кнопки на карточке работают как обычно; за название и телефон
    // тащить можно — просто щелчок по ним по-прежнему открывает ссылку
    if (event.target.closest('button, input, select, textarea, form')) return;

    drag = {
      card: card,
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      touch: event.pointerType !== 'mouse',
      active: false,
    };

    if (drag.touch) {
      card.classList.add('is-pressed');
      drag.timer = setTimeout(function () {
        if (drag && !drag.active) lift(drag.x, drag.y);
      }, LONG_PRESS);
    }
  });

  document.addEventListener('pointermove', function (event) {
    if (!drag || event.pointerId !== drag.id) return;

    if (!drag.active) {
      var moved = Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y);
      // Палец сдвинулся раньше, чем поднял карточку, — это прокрутка
      if (drag.touch) {
        if (moved > 10) cleanup();
        return;
      }
      if (moved < 6) return;
      lift(event.clientX, event.clientY);
    }

    event.preventDefault();
    place(event.clientX, event.clientY);
  }, { passive: false });

  // Пока палец тащит карточку, страница не прокручивается
  document.addEventListener('touchmove', function (event) {
    if (drag && drag.active) event.preventDefault();
  }, { passive: false });

  board.addEventListener('contextmenu', function (event) {
    if (drag) event.preventDefault();
  });

  document.addEventListener('pointerup', function (event) {
    if (!drag || event.pointerId !== drag.id) return;
    var done = drag.active ? drag : null;
    var target = done && done.over;
    var card = drag.card;
    cleanup();
    if (done) {
      // Карточку тащили, а не щёлкали: ссылка под пальцем не открывается
      suppressClick = true;
      setTimeout(function () { suppressClick = false; }, 0);
    }
    if (target) openMove(card, target.dataset.stage, true);
  });

  var suppressClick = false;
  board.addEventListener('click', function (event) {
    if (suppressClick) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  // Своё перетаскивание вместо встроенного у ссылок и картинок
  board.addEventListener('dragstart', function (event) {
    if (event.target.closest && event.target.closest('.sx-card[data-movable]')) event.preventDefault();
  });

  document.addEventListener('pointercancel', cleanup);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') cleanup();
  });
})();
