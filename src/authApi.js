async function parseError(response) {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || JSON.stringify(item)).join('; ')
    }
    return body?.message || `Ошибка ${response.status}`
  } catch {
    return `Ошибка ${response.status}`
  }
}

export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  return response
}

export async function registerAccount(payload) {
  const response = await api('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function loginAccount(payload) {
  const response = await api('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function verifyOtp(payload) {
  const response = await api('/api/auth/verify-otp', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function resendOtp(challengeId) {
  const response = await api('/api/auth/otp/resend', {
    method: 'POST',
    body: JSON.stringify({ challenge_id: challengeId }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

export async function fetchMe() {
  const response = await api('/api/auth/me')
  if (response.status === 401) {
    const refreshed = await api('/api/auth/refresh', { method: 'POST' })
    if (!refreshed.ok) return null
    const again = await api('/api/auth/me')
    if (!again.ok) return null
    return again.json()
  }
  if (!response.ok) return null
  return response.json()
}

export async function logoutAccount() {
  await api('/api/auth/logout', { method: 'POST' })
}

const CHALLENGE_KEY = 'reelsai_auth_challenge'

export function saveChallenge(challenge) {
  sessionStorage.setItem(CHALLENGE_KEY, JSON.stringify(challenge))
}

export function loadChallenge() {
  try {
    const raw = sessionStorage.getItem(CHALLENGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function clearChallenge() {
  sessionStorage.removeItem(CHALLENGE_KEY)
}
