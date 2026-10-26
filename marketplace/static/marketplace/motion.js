/* ServiGo progressive enhancement. All booking/service actions remain native Django forms. */
(function () {
  'use strict';

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const progress = document.getElementById('sgScrollProgress');
  const backTop = document.getElementById('sgBackTop');
  const navbar = document.querySelector('.site-navbar');
  let scrollQueued = false;

  function onScroll() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
    if (progress) progress.style.transform = 'scaleX(' + ratio + ')';
    if (backTop) backTop.classList.toggle('sg-show', window.scrollY > 520);
    if (navbar) navbar.classList.toggle('sg-scrolled', window.scrollY > 12);
    scrollQueued = false;
  }

  window.addEventListener('scroll', function () {
    if (!scrollQueued) {
      scrollQueued = true;
      window.requestAnimationFrame(onScroll);
    }
  }, { passive: true });
  window.addEventListener('resize', onScroll, { passive: true });
  onScroll();

  if (backTop) {
    backTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' });
    });
  }

  /* These effects do not run on devices that request reduced motion. */
  if (reducedMotion || !('IntersectionObserver' in window)) return;

  const targets = Array.from(document.querySelectorAll(
    '.stat-card, .section-topline, .search-panel, .booking-table-wrap, .service-card, ' +
    '.help-strip, .form-shell, .side-tip, .review-card, .profile-header, ' +
    '.auth-illustration, .auth-form, .empty-card, .estimate-side-tip'
  ));

  // Keep stagger short, so long catalogues never feel slow.
  targets.forEach(function (element) {
    const group = element.closest('.stats-grid, .service-section, .review-list');
    if (group) {
      const siblings = Array.from(group.querySelectorAll('.stat-card, .service-card, .review-card'));
      const index = siblings.indexOf(element);
      if (index !== -1) element.style.setProperty('--sg-delay', (Math.min(index % 6, 5) * 65) + 'ms');
    }
    element.classList.add('sg-reveal');
  });

  function animateCount(element) {
    if (!element || element.dataset.sgCounted) return;
    element.dataset.sgCounted = 'true';
    const original = element.textContent.trim();
    const value = Number(original.replace(/,/g, ''));
    if (!/^\d[\d,]*$/.test(original) || !Number.isInteger(value) || value <= 0 || value > 9999) return;
    const started = performance.now();
    const duration = 650;
    element.setAttribute('aria-label', original);
    function tick(now) {
      const t = Math.min((now - started) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      element.textContent = Math.round(value * eased).toLocaleString('en-IN');
      if (t < 1) window.requestAnimationFrame(tick);
      else element.textContent = original;
    }
    window.requestAnimationFrame(tick);
  }

  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('sg-visible');
      if (entry.target.classList.contains('stat-card')) {
        animateCount(entry.target.querySelector('strong'));
      }
      observer.unobserve(entry.target);
    });
  }, { threshold: .08, rootMargin: '0px 0px 28px 0px' });

  targets.forEach(function (element) { observer.observe(element); });
  document.documentElement.classList.add('sg-motion-on');
})();
