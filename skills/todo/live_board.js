(() => {
  const root = document.getElementById('live-board');
  let lastMarkup = root.innerHTML;
  let request = 0;

  viewFor = id => {
    let panel = document.getElementById(id);
    if (!panel) {
      panel = document.createElement('dialog');
      panel.className = 'view';
      panel.id = id;
      panel.innerHTML = '<div class="sheet"><button class="close" aria-label="Закрыть">×</button><p role="status">Загрузка…</p></div>';
      root.querySelector('.layout').append(panel);
    }
    loadDetail(panel);
    return panel;
  };

  function sameLink(container, link) {
    if (!container || !link?.matches('a[href]')) return null;
    return [...container.querySelectorAll('a[href]')].find(a =>
      a.getAttribute('href') === link.getAttribute('href') && a.textContent === link.textContent);
  }

  async function loadDetail(panel) {
    const ticket = ++request;
    try {
      const response = await fetch('/detail?id=' + encodeURIComponent(panel.id), {cache:'no-store'});
      if (!response.ok) throw Error(response.status);
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (ticket !== request || !panel.open || !panel.isConnected) return;
      const incoming = page.querySelector('.sheet');
      if (panel.firstElementChild.isEqualNode(incoming)) return;
      const scroll = panel.scrollTop;
      const active = document.activeElement;
      const focus = panel.contains(active) && (sameLink(incoming, active) || incoming.querySelector('.close'));
      panel.replaceChildren(incoming);
      panel.scrollTop = scroll;
      if (focus) focus.focus({preventScroll:true});
    } catch {
      const status = panel.querySelector('[role=status]');
      if (ticket === request && status) status.textContent = 'Не удалось загрузить описание. Открой карточку ещё раз.';
    }
  }

  function key(el) {
    return el.id || el.classList[0] + ':' + (el.dataset.key || el.closest('.ticket')?.dataset.key || '');
  }

  async function refresh() {
    const response = await fetch('/board.html', {cache:'no-store'});
    if (!response.ok) throw Error(response.status);
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    const incoming = doc.getElementById('live-board');
    const markup = incoming.innerHTML;
    const panel = root.querySelector('dialog[open]');
    if (markup !== lastMarkup) {
      const toggles = new Map([...root.querySelectorAll('details, .fold')].map(el =>
        [key(el), el.matches('details') ? el.open : el.checked]));
      const offsets = new Map([...root.querySelectorAll('.board')].map(el => [key(el), el.scrollLeft]));
      const x = window.scrollX, y = window.scrollY;
      const active = document.activeElement;
      const cardId = active.closest('.card')?.id;
      const id = active?.id, view = active?.dataset.view;
      const summary = active?.matches('summary') ? key(active.parentElement) : null;
      const layout = root.querySelector('.layout');
      layout.firstElementChild.replaceWith(incoming.querySelector('.layout').firstElementChild);
      root.querySelector('.groups')?.remove();
      const groups = incoming.querySelector('.groups');
      if (groups) layout.before(groups);
      lastMarkup = markup;
      document.title = doc.title;
      document.querySelector('style').textContent = doc.querySelector('style').textContent;
      for (const el of root.querySelectorAll('details, .fold')) {
        if (!toggles.has(key(el))) continue;
        if (el.matches('details')) el.open = toggles.get(key(el));
        else el.checked = toggles.get(key(el));
      }
      for (const el of root.querySelectorAll('.board')) el.scrollLeft = offsets.get(key(el)) || 0;
      if (panel && !triggerFor(panel.id)) { panel.close(); panel.remove(); }
      const focus = (id && document.getElementById(id)) || (view && triggerFor(view)) ||
        (cardId && sameLink(document.getElementById(cardId), active)) ||
        (summary && [...root.querySelectorAll('details')].find(el => key(el) === summary)?.firstElementChild);
      if (!active.isConnected && focus) focus.focus({preventScroll:true});
      window.scrollTo(x, y);
    }
    if (panel?.open) await loadDetail(panel);
  }

  let pending = false, updating = false, retry;
  async function update() {
    pending = true;
    if (updating) return;
    updating = true;
    try {
      while (pending) {
        pending = false;
        await refresh();
      }
    } catch {
      clearTimeout(retry);
      retry = setTimeout(update, 1500);
    } finally {
      updating = false;
    }
  }

  new EventSource('/events?since=' + root.dataset.version).onmessage = update;
  const initial = triggerFor(root.dataset.open);
  if (initial) initial.click();
})();
