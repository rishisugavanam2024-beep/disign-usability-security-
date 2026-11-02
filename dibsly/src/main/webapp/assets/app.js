'use strict';
const published = document.querySelector('[data-published-draft]');
if(published) { try { sessionStorage.removeItem(published.dataset.publishedDraft); } catch {} }
const menu = document.querySelector('.menu-toggle');
menu?.addEventListener('click', () => { const open = menu.getAttribute('aria-expanded') !== 'true'; menu.setAttribute('aria-expanded', String(open)); document.getElementById('main-nav').classList.toggle('is-open', open); });
document.addEventListener('keydown', event => { if(event.key === 'Escape' && menu?.getAttribute('aria-expanded') === 'true') { menu.click(); menu.focus(); } });
document.querySelectorAll('[data-password]').forEach(button => button.addEventListener('click', () => {
  const input = document.getElementById(button.dataset.password); const show = input.type === 'password';
  input.type = show ? 'text' : 'password'; button.textContent = show ? 'Hide' : 'Show'; button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
}));
document.querySelectorAll('[data-preview]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-preview]').forEach(other => { const selected = other === button; other.classList.toggle('selected', selected); other.setAttribute('aria-pressed', String(selected)); });
  const alex = button.dataset.preview === 'alex';
  document.getElementById('preview-copy').textContent = alex ? 'Two visual directions, a considered wordmark, and packaging that feels like you.' : 'A discovery workshop, a complete identity, and a recorded handover to make it yours.';
  document.getElementById('preview-support').textContent = alex ? 'Includes 14 days of post-delivery support' : 'Includes 30 days of post-delivery support';
}));
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-filter]').forEach(other => { other.classList.toggle('active', other === button); other.setAttribute('aria-pressed', String(other === button)); });
  let visible = 0;
  document.querySelectorAll('[data-status]').forEach(row => { row.hidden = button.dataset.filter !== 'ALL' && button.dataset.filter !== row.dataset.status; if(!row.hidden) visible++; });
  document.getElementById('workspace-empty').hidden = visible > 0;
}));
document.querySelectorAll('[data-count-for]').forEach(counter => { const input = document.getElementById(counter.dataset.countFor); const update = () => counter.textContent = `${input.value.length} / ${input.maxLength}`; input.addEventListener('input', update); update(); });
// Local drafts never include identity, session tokens, passwords, or permission changes.
document.querySelectorAll('[data-draft]').forEach(form => {
  const names = ['title','category','description','budget','urgency']; const status = form.querySelector('.draft-status');
  try {
    const saved = JSON.parse(sessionStorage.getItem(form.dataset.draft) || 'null');
    if(saved && !form.elements.title.value) { names.forEach(name => { if(typeof saved[name] === 'string') form.elements[name].value = saved[name]; }); status.textContent = 'Your draft was restored in this tab.'; form.elements.description.dispatchEvent(new Event('input')); }
    form.addEventListener('input', () => { const draft = {}; names.forEach(name => draft[name] = form.elements[name].value); try { sessionStorage.setItem(form.dataset.draft, JSON.stringify(draft)); status.textContent = 'Draft saved in this tab.'; } catch { status.textContent = 'Draft storage is unavailable. Keep this tab open.'; } });
  } catch { status.textContent = 'Draft storage is unavailable. Keep this tab open.'; }
});
document.querySelectorAll('form[method="post"]').forEach(form => form.addEventListener('submit', event => {
  if(form.dataset.confirm && !window.confirm(form.dataset.confirm)) { event.preventDefault(); return; }
  if(!form.checkValidity()) return;
  if(form.dataset.submitting) { event.preventDefault(); return; }
  form.dataset.submitting = 'true';
  const button = form.querySelector('button[type="submit"]');
  if(button) { button.dataset.originalText = button.innerHTML; button.disabled = true; button.textContent = 'One moment…'; }
}));
window.addEventListener('pageshow', () => { document.querySelectorAll('form[data-submitting]').forEach(form => { delete form.dataset.submitting; const button = form.querySelector('button[type="submit"]'); if(button?.dataset.originalText) { button.innerHTML = button.dataset.originalText; button.disabled = false; } }); });
