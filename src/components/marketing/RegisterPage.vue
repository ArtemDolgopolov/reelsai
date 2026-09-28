<script setup>
import { ref } from 'vue'
import { ArrowRight, AtSign, Eye, EyeOff, Lock, Mail, User, Zap } from '@lucide/vue'

const emit = defineEmits(['navigate', 'enter'])

const name = ref('')
const email = ref('')
const username = ref('')
const password = ref('')
const agree = ref(false)
const showPassword = ref(false)

function onSubmit() {
  if (!agree.value) return
  emit('enter')
}
</script>

<template>
  <div class="mkt-shell mkt-auth">
    <div class="mkt-auth-top">
      <button class="mkt-logo" type="button" @click="$emit('navigate', 'landing')">
        <span class="mkt-logo-mark"><Zap :size="18" fill="currentColor" /></span>
        AI Рилс Продюсер
      </button>
      <p class="mkt-auth-foot" style="margin: 0">
        Уже есть аккаунт?
        <button class="mkt-link" type="button" @click="$emit('navigate', 'login')">Войти</button>
      </p>
    </div>

    <span class="mkt-doodle mkt-auth-doodle tl">Создавай больше,<br />чем смотрят ✈</span>
    <span class="mkt-doodle mkt-auth-doodle tr">♛</span>
    <span class="mkt-doodle mkt-auth-doodle bl">✦</span>
    <span class="mkt-doodle mkt-auth-doodle br">★</span>

    <form class="mkt-auth-card wide" @submit.prevent="onSubmit">
      <h1>Создай аккаунт</h1>
      <p>Начни создавать вирусные рилсы с помощью ИИ уже сегодня.</p>

      <div class="mkt-field">
        <label for="reg-name">Как вас зовут</label>
        <div class="mkt-input-wrap">
          <User :size="16" />
          <input
            id="reg-name"
            v-model="name"
            type="text"
            autocomplete="name"
            placeholder="Имя"
            required
          />
        </div>
      </div>

      <div class="mkt-field">
        <label for="reg-email">Email</label>
        <div class="mkt-input-wrap">
          <Mail :size="16" />
          <input
            id="reg-email"
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="you@email.com"
            required
          />
        </div>
      </div>

      <div class="mkt-field">
        <label for="reg-username">Имя пользователя (необязательно)</label>
        <div class="mkt-input-wrap">
          <AtSign :size="16" />
          <input
            id="reg-username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="username"
          />
        </div>
      </div>

      <div class="mkt-field">
        <label for="reg-password">Пароль</label>
        <div class="mkt-input-wrap">
          <Lock :size="16" />
          <input
            id="reg-password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="new-password"
            placeholder="Минимум 8 символов"
            minlength="8"
            required
          />
          <button
            class="mkt-eye"
            type="button"
            :aria-label="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
            @click="showPassword = !showPassword"
          >
            <EyeOff v-if="showPassword" :size="16" />
            <Eye v-else :size="16" />
          </button>
        </div>
      </div>

      <label class="mkt-check mkt-terms">
        <input v-model="agree" type="checkbox" required />
        <span>
          Я соглашаюсь с
          <button class="mkt-link" type="button">Условиями использования</button>
          и
          <button class="mkt-link" type="button">Политикой конфиденциальности</button>
        </span>
      </label>

      <button class="mkt-btn mkt-btn-primary mkt-btn-lg" type="submit">
        Зарегистрироваться
        <ArrowRight :size="18" />
      </button>

      <div class="mkt-divider">или через</div>
      <div class="mkt-social">
        <button type="button" @click="agree && onSubmit()">
          <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="#EA4335"
              d="M12 10.2v3.6h5.1c-.2 1.2-.9 2.3-1.9 3l3.1 2.4c1.8-1.7 2.9-4.1 2.9-7 0-.7-.1-1.3-.2-1.9H12z"
            />
            <path
              fill="#34A853"
              d="M6.6 14.3l-.7.5-2.4 1.9C5.1 19.3 8.3 21.2 12 21.2c2.2 0 4.1-.7 5.5-2l-3.1-2.4c-.8.5-1.9.9-3 .9-2.3 0-4.2-1.5-4.9-3.6z"
            />
            <path
              fill="#4A90E2"
              d="M3.5 7.3C2.9 8.5 2.5 9.9 2.5 11.4s.4 2.9 1 4.1l3.1-2.4c-.2-.5-.3-1.1-.3-1.7s.1-1.2.3-1.7L3.5 7.3z"
            />
            <path
              fill="#FBBC05"
              d="M12 5.8c1.2 0 2.3.4 3.2 1.2l2.4-2.4C16.1 3.2 14.2 2.4 12 2.4 8.3 2.4 5.1 4.3 3.5 7.3l3.1 2.4C7.3 7.6 9.3 5.8 12 5.8z"
            />
          </svg>
          Google
        </button>
        <button type="button" @click="agree && onSubmit()">
          <svg width="14" height="16" viewBox="0 0 14 17" aria-hidden="true">
            <path
              fill="currentColor"
              d="M13.2 5.8c-.1 0-1.5-.9-2.5-.9-1.2 0-2.2.7-2.8.7-.6 0-1.5-.7-2.5-.7C3.5 4.9 2 6.1 2 8.5c0 1.6.6 3.3 1.4 4.4.6.8 1.2 1.5 2 1.5.8 0 1.1-.5 2.1-.5s1.3.5 2.1.5c.9 0 1.4-.7 2-.1.3.1 1.1-1.3 1.1-1.3s-1.9-.8-1.9-3.1c0-2 1.6-2.9 1.6-2.9s-1.1-1.7-2.2-1.8zM8.7 3.5c.5-.6.9-1.5.8-2.4-.8.1-1.7.5-2.3 1.2-.5.5-.9 1.4-.8 2.2.9.1 1.7-.4 2.3-1z"
            />
          </svg>
          Apple
        </button>
      </div>
    </form>
  </div>
</template>
