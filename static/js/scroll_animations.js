/**
 * scroll_animations.js — Scroll-triggered reveal animations,
 * counter animations, navbar scroll effects, and smooth anchor links.
 *
 * Used on the home / landing page.
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const REVEAL_THRESHOLD = 0.15;
  const COUNTER_THRESHOLD = 0.5;
  const COUNTER_DURATION_MS = 2000;
  const NAVBAR_SCROLL_OFFSET = 50;

  // ── Scroll reveal ──────────────────────────────────────────
  const reveal_observer = new IntersectionObserver(
    function (entries) {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
        }
      }
    },
    { threshold: REVEAL_THRESHOLD }
  );

  document.querySelectorAll('.reveal').forEach(function (element) {
    reveal_observer.observe(element);
  });

  // ── Navbar scroll effect ───────────────────────────────────
  const navbar = document.getElementById('navbar');

  if (navbar) {
    window.addEventListener('scroll', function () {
      const is_scrolled = window.scrollY > NAVBAR_SCROLL_OFFSET;
      navbar.classList.toggle('scrolled', is_scrolled);
    });
  }

  // ── Counter animation ─────────────────────────────────────
  function ease_out_quart(progress) {
    return 1 - Math.pow(1 - progress, 4);
  }

  const counter_observer = new IntersectionObserver(
    function (entries) {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;

        const element = entry.target;
        const target_value = parseFloat(element.dataset.target);
        const decimal_places = parseInt(element.dataset.decimals || '0', 10);
        const start_time = performance.now();

        function tick(current_time) {
          const elapsed = current_time - start_time;
          const progress = Math.min(elapsed / COUNTER_DURATION_MS, 1);
          const eased = ease_out_quart(progress);
          const current_value = eased * target_value;

          element.textContent = current_value.toFixed(decimal_places);

          if (progress < 1) {
            requestAnimationFrame(tick);
          } else {
            element.textContent = target_value.toFixed(decimal_places);
          }
        }

        requestAnimationFrame(tick);
        counter_observer.unobserve(element);
      }
    },
    { threshold: COUNTER_THRESHOLD }
  );

  document.querySelectorAll('.stat-num[data-target]').forEach(function (element) {
    counter_observer.observe(element);
  });

  // ── Smooth anchor scrolling ────────────────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(function (link) {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      const target_selector = link.getAttribute('href');
      const target_element = document.querySelector(target_selector);

      if (target_element) {
        target_element.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
})();
