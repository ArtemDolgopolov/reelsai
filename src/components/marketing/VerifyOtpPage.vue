<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, KeyRound, LoaderCircle, Zap } from '@lucide/vue'
import { clearChallenge, loadChallenge, resendOtp, saveChallenge, verifyOtp } from '../../authApi.js'

const emit = defineEmits(['navigate', 'entered'])

const code = ref('')
const busy = ref(false)
const resendBusy = ref(false)
const error = ref('')
const challenge = ref(loadChallenge())
const debugCode = computed(() => challenge.value?.debug_code || '')

onMounted(() => {
  if (!challenge.value?.challenge_id) {
    emit('navigate', 'login')
  }
})

async function onSubmit() {
  if (!challenge.value?.challenge_id) return
  busy.value = true
  error.value = ''
  try {
    await verifyOtp({
      challenge_id: challenge.value.challenge_id,
      code: code.value.trim(),
    })
    clearChallenge()
    emit('entered')
  } catch (err) {
    error.value = err.message || 'Не удалось подтвердить код'
  } finally {
    busy.value = false
  }
}

async function onResend() {
  if (!challenge.value?.challenge_id) return
  resendBusy.value = true
  error.value = ''
  try {
    const next = await resendOtp(challenge.value.challenge_id)
    challenge.value = next
    saveChallenge(next)
  } catch (err) {
    error.value = err.message || 'Не удалось отправить код снова'
  } finally {
    resendBusy.value = false
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
    </div>

    <span class="mkt-doodle mkt-auth-doodle tl">Проверьте почту ✉</span>
    <span class="mkt-doodle mkt-auth-doodle tr">✦</span>

    <form class="mkt-auth-card" @submit.prevent="onSubmit">
      <h1>Код подтверждения</h1>
      <p>
        Мы отправили 6-значный код на
        <strong>{{ challenge?.email_masked || 'вашу почту' }}</strong>.
        Введите его, чтобы продолжить.
      </p>

      <div class="mkt-field">
        <label for="otp-code">Код из письма</label>
        <div class="mkt-input-wrap">
          <KeyRound :size="16" />
          <input
            id="otp-code"
            v-model="code"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            placeholder="123456"
            maxlength="12"
            required
          />
        </div>
      </div>

      <p v-if="debugCode" class="mkt-auth-foot" style="margin-bottom: 12px">
        Dev-код: <strong>{{ debugCode }}</strong>
      </p>
      <p v-if="error" class="mkt-auth-foot" style="color: #be123c; margin-bottom: 12px">{{ error }}</p>

      <button class="mkt-btn mkt-btn-primary mkt-btn-lg" type="submit" :disabled="busy">
        <LoaderCircle v-if="busy" :size="18" class="spin" />
        <template v-else>
          Подтвердить
          <ArrowRight :size="18" />
        </template>
      </button>

      <p class="mkt-auth-foot">
        Не пришло письмо?
        <button class="mkt-link" type="button" :disabled="resendBusy" @click="onResend">
          {{ resendBusy ? 'Отправляем…' : 'Отправить снова' }}
        </button>
      </p>
      <p class="mkt-auth-foot" style="margin-top: 10px">
        <button class="mkt-link" type="button" @click="$emit('navigate', 'login')">Назад ко входу</button>
      </p>
    </form>
  </div>
</template>
