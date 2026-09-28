<script setup>
import { ref } from 'vue'
import { ArrowRight, AtSign, Eye, EyeOff, LoaderCircle, Lock, Mail, User, Zap } from '@lucide/vue'
import { registerAccount, saveChallenge } from '../../authApi.js'

const emit = defineEmits(['navigate'])

const name = ref('')
const email = ref('')
const username = ref('')
const password = ref('')
const agree = ref(false)
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')

async function onSubmit() {
  if (!agree.value) {
    error.value = 'Нужно принять условия использования'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const challenge = await registerAccount({
      email: email.value.trim(),
      password: password.value,
      name: name.value.trim() || null,
      username: username.value.trim() || null,
    })
    saveChallenge(challenge)
    emit('navigate', 'verify-otp')
  } catch (err) {
    error.value = err.message || 'Не удалось зарегистрироваться'
  } finally {
    busy.value = false
  }
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

      <p v-if="error" class="mkt-auth-foot" style="color: #be123c; margin-bottom: 12px">{{ error }}</p>

      <button class="mkt-btn mkt-btn-primary mkt-btn-lg" type="submit" :disabled="busy">
        <LoaderCircle v-if="busy" :size="18" class="spin" />
        <template v-else>
          Зарегистрироваться
          <ArrowRight :size="18" />
        </template>
      </button>

      <div class="mkt-divider">или через</div>
      <div class="mkt-social">
        <button type="button" disabled title="Скоро — фаза 2">Google</button>
        <button type="button" disabled title="Скоро — фаза 2">Яндекс</button>
      </div>
    </form>
  </div>
</template>
