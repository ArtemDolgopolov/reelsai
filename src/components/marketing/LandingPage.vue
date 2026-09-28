<script setup>
import {
  ArrowRight,
  Eye,
  Film,
  Lightbulb,
  Play,
  Sparkles,
  TrendingUp,
  WandSparkles,
  Zap,
} from '@lucide/vue'

defineEmits(['navigate'])
</script>

<template>
  <div class="mkt-shell mkt-landing">
    <header class="mkt-header">
      <button class="mkt-logo" type="button" @click="$emit('navigate', 'landing')">
        <span class="mkt-logo-mark"><Zap :size="18" fill="currentColor" /></span>
        AI Рилс Продюсер
      </button>
      <nav class="mkt-nav" aria-label="Навигация">
        <a href="#landing">Возможности</a>
        <a href="#landing">Тарифы</a>
        <a href="#landing">Блог</a>
      </nav>
      <div class="mkt-header-actions">
        <button class="mkt-btn mkt-btn-ghost" type="button" @click="$emit('navigate', 'login')">
          Войти
        </button>
        <button class="mkt-btn mkt-btn-primary" type="button" @click="$emit('navigate', 'register')">
          Зарегистрироваться
        </button>
      </div>
    </header>

    <section class="mkt-hero">
      <div>
        <span class="mkt-badge"><Sparkles :size="14" /> Твой AI-помощник по рилс</span>
        <h1>Анализируй.<br />Вдохновляйся.<br />Создавай быстрее.</h1>
        <p class="mkt-hero-copy">
          Находит трендовые рилсы, анализирует структуру и помогает создавать ваши версии с помощью ИИ.
        </p>
        <div class="mkt-hero-ctas">
          <button class="mkt-btn mkt-btn-primary mkt-btn-lg" type="button" @click="$emit('navigate', 'register')">
            Попробовать бесплатно
            <ArrowRight :size="18" />
          </button>
          <button class="mkt-btn mkt-btn-outline mkt-btn-lg" type="button" @click="$emit('navigate', 'login')">
            <Play :size="16" fill="currentColor" />
            Смотреть демо
          </button>
        </div>
        <div class="mkt-feature-row">
          <div class="mkt-feature">
            <span class="mkt-feature-icon"><TrendingUp :size="16" /></span>
            <div>
              <strong>Трендовые идеи каждый день</strong>
              <span>Свежие рилсы конкурентов в одной ленте</span>
            </div>
          </div>
          <div class="mkt-feature">
            <span class="mkt-feature-icon"><Lightbulb :size="16" /></span>
            <div>
              <strong>Анализ что работает</strong>
              <span>Хук, структура, CTA и охваты</span>
            </div>
          </div>
          <div class="mkt-feature">
            <span class="mkt-feature-icon"><WandSparkles :size="16" /></span>
            <div>
              <strong>ИИ помогает создать вашу версию</strong>
              <span>Remix сценария под ваш голос</span>
            </div>
          </div>
        </div>
      </div>

      <div class="mkt-stage" aria-hidden="true">
        <span class="mkt-doodle mkt-scribble a">Из трендов<br />в твой контент ✦</span>
        <span class="mkt-doodle mkt-scribble b">idea → reel</span>
        <span class="mkt-star s1">✦</span>
        <span class="mkt-star s2">★</span>
        <span class="mkt-star s3">✧</span>

        <div class="mkt-phone">
          <img
            src="https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?auto=format&fit=crop&w=600&q=80"
            alt=""
          />
          <span class="mkt-phone-views"><Eye :size="12" /> 1.2M</span>
          <span class="mkt-phone-caption">IDEA TO REEL<br />IN 10 MIN</span>
        </div>

        <div class="mkt-robot">🤖</div>

        <aside class="mkt-card-float mkt-analysis">
          <h3>Анализ рилса</h3>
          <ul>
            <li><span><TrendingUp :size="12" /></span> Охваты</li>
            <li><span><Film :size="12" /></span> Структура</li>
            <li><span><Zap :size="12" /></span> Хук</li>
            <li><span><Play :size="12" /></span> Музыка</li>
            <li><span><Lightbulb :size="12" /></span> Что улучшить</li>
          </ul>
        </aside>

        <aside class="mkt-card-float mkt-version">
          <h3>Ваша версия с ИИ</h3>
          <div class="mkt-thumbs">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <button class="mkt-btn mkt-btn-primary" type="button" tabindex="-1">
            Сгенерировать сценарий
          </button>
        </aside>
      </div>
    </section>

    <section class="mkt-proof">
      <div class="mkt-proof-text">
        <div class="mkt-avatars" aria-hidden="true">
          <i></i><i></i><i></i><i></i>
        </div>
        <p>
          Уже более <strong>10 000 креаторов</strong> создают контент с AI Рилс Продюсер
        </p>
      </div>
      <div class="mkt-review">
        <span class="mkt-stars">★★★★★</span>
        <span>«Экономит часы работы и дает классные идеи!»</span>
      </div>
    </section>

    <footer class="mkt-platforms" aria-label="Платформы">
      <span>YouTube</span>
      <span>Instagram</span>
      <span>TikTok</span>
      <span>Meta</span>
    </footer>
  </div>
</template>
