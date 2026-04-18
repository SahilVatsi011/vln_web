/**
 * particles.js — Canvas particle system for the home page.
 *
 * Creates floating particles with mouse-repulsion physics
 * and draws connection lines between nearby particles.
 * Self-contained IIFE — no global pollution.
 */

(function () {
  'use strict';

  // ── Configuration ──────────────────────────────────────────
  const MAX_PARTICLES = 120;
  const PARTICLE_DENSITY = 0.08;
  const CONNECTION_DISTANCE = 140;
  const MOUSE_REPULSION_RADIUS = 120;
  const MOUSE_REPULSION_FORCE = 1.5;
  const PARTICLE_SPEED = 0.3;
  const CONNECTION_OPACITY = 0.06;
  const HUE_BLUE = 220;
  const HUE_CYAN = 190;

  // ── Canvas setup ───────────────────────────────────────────
  const canvas = document.getElementById('particles');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const particles = [];
  const mouse = { x: -1000, y: -1000 };

  function resize_canvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  resize_canvas();
  window.addEventListener('resize', resize_canvas);
  document.addEventListener('mousemove', function (event) {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
  });

  // ── Particle ───────────────────────────────────────────────

  class Particle {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * canvas.width;
      this.y = Math.random() * canvas.height;
      this.size = Math.random() * 1.5 + 0.3;
      this.speed_x = (Math.random() - 0.5) * PARTICLE_SPEED;
      this.speed_y = (Math.random() - 0.5) * PARTICLE_SPEED;
      this.opacity = Math.random() * 0.5 + 0.1;
      this.hue = Math.random() > 0.5 ? HUE_BLUE : HUE_CYAN;
    }

    update() {
      this.x += this.speed_x;
      this.y += this.speed_y;

      // Mouse repulsion
      const delta_x = this.x - mouse.x;
      const delta_y = this.y - mouse.y;
      const distance = Math.sqrt(delta_x * delta_x + delta_y * delta_y);

      if (distance < MOUSE_REPULSION_RADIUS) {
        this.x += (delta_x / distance) * MOUSE_REPULSION_FORCE;
        this.y += (delta_y / distance) * MOUSE_REPULSION_FORCE;
      }

      // Wrap around or reset when out of bounds
      const is_out_of_bounds = (
        this.x < 0 || this.x > canvas.width ||
        this.y < 0 || this.y > canvas.height
      );
      if (is_out_of_bounds) {
        this.reset();
      }
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${this.hue}, 80%, 70%, ${this.opacity})`;
      ctx.fill();
    }
  }

  // ── Initialization ─────────────────────────────────────────
  const particle_count = Math.min(
    MAX_PARTICLES,
    Math.floor(window.innerWidth * PARTICLE_DENSITY)
  );

  for (let index = 0; index < particle_count; index++) {
    particles.push(new Particle());
  }

  // ── Drawing ────────────────────────────────────────────────

  function draw_connections() {
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const delta_x = particles[i].x - particles[j].x;
        const delta_y = particles[i].y - particles[j].y;
        const distance = Math.sqrt(delta_x * delta_x + delta_y * delta_y);

        if (distance < CONNECTION_DISTANCE) {
          const alpha = CONNECTION_OPACITY * (1 - distance / CONNECTION_DISTANCE);
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
  }

  function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (const particle of particles) {
      particle.update();
      particle.draw();
    }

    draw_connections();
    requestAnimationFrame(animate);
  }

  animate();
})();
