<script setup>
import { onMounted, ref } from 'vue'
import { ArrowRight, Eye, EyeOff, LoaderCircle, Lock, Mail, WandSparkles } from '@lucide/vue'
import { fetchOauthProviders, loginAccount, oauthStartUrl, saveChallenge } from '../../authApi.js'

const emit = defineEmits(['navigate'])

const email = ref('')
const password = ref('')
const remember = ref(true)
const showPassword = ref(false)
const busy = ref(false)
const error = ref('')
const providers = ref({ google: false, yandex: false })

onMounted(async () => {
  providers.value = await fetchOauthProviders()
  try {
    const stored = sessionStorage.getItem('reelsai_oauth_error')
    if (stored) {
      error.value = stored
      sessionStorage.removeItem('reelsai_oauth_error')
    }
  } catch {
    // ignore
  }
})

async function onSubmit() {
  busy.value = true
  error.value = ''
  try {
    const challenge = await loginAccount({
      email: email.value.trim(),
      password: password.value,
    })
    saveChallenge(challenge)
    emit('navigate', 'verify-otp')
  } catch (err) {
    error.value = err.message || 'Не удалось войти'
  } finally {
    busy.value = false
  }
}

function startOauth(provider) {
  window.location.href = oauthStartUrl(provider)
}
</script>

<template>
  <div class="mkt-shell mkt-auth">
    <div class="mkt-auth-top">
      <button class="mkt-logo" type="button" @click="$emit('navigate', 'landing')">
        <span class="mkt-logo-mark"><WandSparkles :size="19" /></span>
        Reels Finder
      </button>
    </div>

    <span class="mkt-doodle mkt-auth-doodle tl">С возвращением! ♥</span>
    <span class="mkt-doodle mkt-auth-doodle tr">✦</span>
    <span class="mkt-doodle mkt-auth-doodle bl">★</span>
    <span class="mkt-doodle mkt-auth-doodle br">✧</span>

    <form class="mkt-auth-card" @submit.prevent="onSubmit">
      <div class="mkt-auth-robot" aria-hidden="true">🤖</div>
      <h1>Снова вместе!</h1>
      <p>Войдите, чтобы продолжить создавать крутые рилсы с ИИ.</p>

      <div class="mkt-field">
        <label for="login-email">Email</label>
        <div class="mkt-input-wrap">
          <Mail :size="16" />
          <input
            id="login-email"
            v-model="email"
            type="email"
            autocomplete="email"
            placeholder="you@email.com"
            required
          />
        </div>
      </div>

      <div class="mkt-field">
        <label for="login-password">Пароль</label>
        <div class="mkt-input-wrap">
          <Lock :size="16" />
          <input
            id="login-password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="Введите пароль"
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

      <div class="mkt-auth-row">
        <label class="mkt-check">
          <input v-model="remember" type="checkbox" />
          Запомнить меня
        </label>
        <button class="mkt-link" type="button">Забыли пароль?</button>
      </div>

      <p v-if="error" class="mkt-auth-foot" style="color: #be123c; margin-bottom: 12px">{{ error }}</p>

      <button class="mkt-btn mkt-btn-primary mkt-btn-lg" type="submit" :disabled="busy">
        <LoaderCircle v-if="busy" :size="18" class="spin" />
        <template v-else>
          Войти
          <ArrowRight :size="18" />
        </template>
      </button>

      <div class="mkt-divider">или войти через</div>
      <div class="mkt-social">
        <button
          type="button"
          :disabled="!providers.google"
          :title="providers.google ? 'Войти через Google' : 'Добавьте GOOGLE_CLIENT_ID в .env'"
          @click="startOauth('google')"
        >
          Google
        </button>
        <button
          type="button"
          :disabled="!providers.yandex"
          :title="providers.yandex ? 'Войти через Яндекс' : 'Добавьте YANDEX_CLIENT_ID в .env'"
          @click="startOauth('yandex')"
        >
          Яндекс
        </button>
      </div>

      <p class="mkt-auth-foot">
        Еще нет аккаунта?
        <button class="mkt-link" type="button" @click="$emit('navigate', 'register')">Регистрация</button>
      </p>
    </form>
  </div>
</template>
