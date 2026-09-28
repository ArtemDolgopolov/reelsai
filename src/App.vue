<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  ArrowUpRight,
  Camera,
  Check,
  CircleCheck,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clapperboard,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Heart,
  Home,
  Hourglass,
  Lightbulb,
  LoaderCircle,
  MessageCircle,
  MoreVertical,
  Pencil,
  Pause,
  Play,
  Save,
  Search,
  Sparkles,
  Target,
  Timer,
  Trash2,
  UserRound,
  Users,
  Volume2,
  VolumeX,
  WandSparkles,
  X,
  Zap,
} from '@lucide/vue'
import LandingPage from './components/marketing/LandingPage.vue'
import LoginPage from './components/marketing/LoginPage.vue'
import RegisterPage from './components/marketing/RegisterPage.vue'
import VerifyOtpPage from './components/marketing/VerifyOtpPage.vue'
import { claimOauthTicket, clearChallenge, fetchMe, logoutAccount } from './authApi.js'

const marketingPages = ['landing', 'login', 'register', 'verify-otp']
const appPages = ['home', 'plan', 'competitors', 'detail']
const pages = [...marketingPages, ...appPages]

function parseLocationHash() {
  const raw = window.location.hash.replace(/^#/, '').trim()
  const query = new URLSearchParams(window.location.search)
  // OAuth callback lands on /?auth=... (hash is unreliable on 302).
  if (query.get('auth') === 'verify-otp') {
    return { page: 'verify-otp', reelId: null, competitorId: null }
  }
  if (query.get('auth') === 'home') {
    return { page: 'home', reelId: null, competitorId: null }
  }
  if (!raw) {
    if (query.get('oauth_error')) {
      return { page: 'login', reelId: null, competitorId: null }
    }
    return {
      page: 'landing',
      reelId: null,
      competitorId: null,
    }
  }
  const [pagePart, ...rest] = raw.split('/')
  let page = pages.includes(pagePart) ? pagePart : null
  if (!page) page = 'landing'
  const reelId = page === 'detail' && rest[0] ? rest[0] : null
  const competitorId = page === 'competitors' && rest[0] ? rest[0] : null
  return { page, reelId, competitorId }
}

const initialRoute = parseLocationHash()
const currentPage = ref(initialRoute.page)
const currentUser = ref(null)
const authBooting = ref(true)
const userLabel = computed(() => {
  if (!currentUser.value) return ''
  return currentUser.value.name || currentUser.value.email || ''
})
const userEmail = computed(() => currentUser.value?.email || '')
const searchQuery = ref('')
const competitorHandle = ref('')
const competitorsList = ref([])
const competitor = ref(null)
const competitorReels = ref([])
const competitorMessage = ref('')
const competitorLoading = ref(false)
const competitorOpening = ref(false)
const competitorAvatarBroken = ref(false)
const competitorListAvatarBroken = ref({})
const selectedCompetitorId = ref(initialRoute.competitorId)
const homeReels = ref([])
const homeLoading = ref(true)
const planItems = ref([])
const planLoading = ref(false)
const planBusyReelId = ref(null)
const planBusyItemId = ref(null)
const planMessage = ref('')
const expandedPlanIds = ref({})
const remixMode = ref(false)
const remixLoading = ref(false)
const remixMessage = ref('')
const selectedReel = ref(null)
const detailLoading = ref(Boolean(initialRoute.page === 'detail' && initialRoute.reelId))
const detailVideo = ref(null)
const videoPlaying = ref(false)
const videoMuted = ref(true)
const videoVolume = ref(0.7)
const videoProgressPct = ref(0)
const videoCurrentLabel = ref('0:00')
const videoBusy = ref(false)
const showVideoChrome = ref(false)
const editingSection = ref(null)
const draft = ref('')
const saveState = ref('idle')
const saveError = ref('')
const copiedSection = ref('')
const speechPolling = ref(false)
const analysisRevealKey = ref(0)

let speechPollTimer = null
let copiedTimer = null
let chromeIdleTimer = null
const CHROME_IDLE_MS = 2200

const sectionLimits = {
  hook: 200,
  script: 2000,
  cta: 500,
}

const scriptLines = computed(() =>
  (selectedReel.value?.script || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean),
)

const scriptBody = computed(() => {
  const raw = selectedReel.value?.script || ''
  const joined = scriptLines.value.length > 1 ? scriptLines.value.join(' ') : raw
  return joined.replace(/\s+/g, ' ').trim()
})

/** Original-language sections for normal reel view (translation only after Remix). */
const viewOriginalHook = computed(() => (selectedReel.value?.original_hook || '').trim())
const viewOriginalScript = computed(() => (selectedReel.value?.original_script || '').trim())
const viewOriginalCta = computed(() => (selectedReel.value?.original_cta || '').trim())

const overviewParagraphs = computed(() =>
  (selectedReel.value?.overview || '')
    .split(/\n\n+/)
    .map((part) => part.trim())
    .filter(Boolean),
)

const isOverviewStub = computed(() => {
  const text = (selectedReel.value?.overview || '').toLowerCase()
  return (
    text.includes('собираю объяснение') ||
    text.includes('через пару секунд') ||
    text.includes('собираю разбор') ||
    text.includes('кратко по речи автора') ||
    text.includes('готовлю короткое объяснение')
  )
})

const hasRemixDrafts = computed(() => {
  const reel = selectedReel.value
  if (!reel) return false
  return Boolean(
    (reel.original_hook || reel.hook || '').trim() ||
      (reel.original_script || reel.script || '').trim() ||
      (reel.original_cta || reel.cta || '').trim(),
  )
})

const isAnalysisLoading = computed(() => {
  const reel = selectedReel.value
  if (!reel) return false
  if (remixLoading.value && !hasRemixDrafts.value) return true
  // If Hook/Script already exist, never blank the whole column behind skeletons.
  if (hasRemixDrafts.value) return false
  return Boolean(reel.speech_pending || reel.analysis_pending || speechPolling.value)
})

const isOverviewLoading = computed(() => {
  const reel = selectedReel.value
  if (!reel) return false
  return Boolean(
    reel.speech_pending ||
      (reel.analysis_pending && isOverviewStub.value) ||
      (speechPolling.value && isOverviewStub.value),
  )
})

const filteredReels = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return homeReels.value
  return homeReels.value.filter(
    (reel) =>
      reel.title.toLowerCase().includes(query) ||
      reel.author.toLowerCase().includes(query),
  )
})

const selectedDurationLabel = computed(() => selectedReel.value?.duration || '0:00')
const selectedViewsLabel = computed(() => formatViews(selectedReel.value?.views_count || 0))
const selectedInPlan = computed(() =>
  selectedReel.value ? Boolean(planEntryForReel(selectedReel.value.id) || selectedReel.value.in_plan) : false,
)

function planEntryForReel(reelId) {
  if (!reelId) return null
  return planItems.value.find((item) => item.reel_id === reelId) || null
}

function shootStatusLabel(status) {
  if (status === 'done') return 'Снят и выложен'
  if (status === 'ready') return 'Ждёт съёмки'
  return 'Не взят в работу'
}

function formatPostedAt(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const year = date.getFullYear()
  return `${day}.${month}.${year}`
}

function syncReelPlanFields(reelId, entry) {
  const patch = (list) =>
    list.map((reel) =>
      reel.id === reelId
        ? {
            ...reel,
            in_plan: Boolean(entry),
            plan_item_id: entry?.id || null,
            shoot_status: entry?.shoot_status || null,
          }
        : reel,
    )
  homeReels.value = patch(homeReels.value)
  competitorReels.value = patch(competitorReels.value)
}

function formatViews(count) {
  if (count >= 1_000_000) {
    const value = count / 1_000_000
    return `${value >= 10 ? value.toFixed(0) : value.toFixed(1).replace(/\.0$/, '')}M`
  }
  if (count >= 1_000) {
    const value = count / 1_000
    return `${value >= 10 ? value.toFixed(0) : value.toFixed(1).replace(/\.0$/, '')}K`
  }
  return String(count)
}

function formatFollowers(count) {
  return formatViews(count)
}

function formatRelativeTime(value) {
  if (!value) return 'обновлено'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'обновлено'
  const diffSec = Math.round((Date.now() - date.getTime()) / 1000)
  if (diffSec < 90) return 'только что'
  if (diffSec < 3600) return `${Math.max(1, Math.round(diffSec / 60))} мин назад`
  if (diffSec < 86400) return `${Math.max(1, Math.round(diffSec / 3600))} ч назад`
  if (diffSec < 86400 * 7) return `${Math.max(1, Math.round(diffSec / 86400))} дн назад`
  return 'обновлено'
}

function competitorInitial(person) {
  const name = (person?.full_name || person?.username || '?').trim()
  return name.slice(0, 1).toUpperCase()
}

function onCompetitorAvatarError() {
  competitorAvatarBroken.value = true
}

function thumbSrc(url) {
  if (!url) return ''
  if (url.startsWith('/api/media/proxy')) return url
  return `/api/media/proxy?url=${encodeURIComponent(url)}`
}

function videoSrc(url) {
  if (!url) return ''
  if (url.startsWith('/api/media/video')) return url
  return `/api/media/video?url=${encodeURIComponent(url)}`
}

const playbackSrc = computed(() => videoSrc(selectedReel.value?.video_url || ''))

function formatClock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function clearChromeIdleTimer() {
  if (chromeIdleTimer) {
    window.clearTimeout(chromeIdleTimer)
    chromeIdleTimer = null
  }
}

function scheduleChromeHide() {
  clearChromeIdleTimer()
  if (!videoPlaying.value) return
  chromeIdleTimer = window.setTimeout(() => {
    showVideoChrome.value = false
    chromeIdleTimer = null
  }, CHROME_IDLE_MS)
}

function revealVideoChrome() {
  showVideoChrome.value = true
  scheduleChromeHide()
}

function hideVideoChrome() {
  clearChromeIdleTimer()
  showVideoChrome.value = false
}

function resetVideoUi() {
  videoPlaying.value = false
  videoProgressPct.value = 0
  videoCurrentLabel.value = '0:00'
  videoBusy.value = false
  hideVideoChrome()
  const el = detailVideo.value
  if (el) {
    try {
      el.pause()
      el.currentTime = 0
    } catch {
      // ignore
    }
  }
}

function onVideoTimeUpdate() {
  const el = detailVideo.value
  if (!el || !el.duration) return
  videoProgressPct.value = Math.min(100, (el.currentTime / el.duration) * 100)
  videoCurrentLabel.value = formatClock(el.currentTime)
}

function onVideoPlay() {
  videoPlaying.value = true
  if (showVideoChrome.value) scheduleChromeHide()
}

function onVideoPause() {
  videoPlaying.value = false
  clearChromeIdleTimer()
}

async function refreshPlaybackUrl() {
  const reelId = selectedReel.value?.id
  if (!reelId) return false
  try {
    const response = await fetch(`/api/reels/${reelId}/refresh-video`, { method: 'POST' })
    if (!response.ok) return false
    const body = await response.json()
    if (selectedReel.value?.id === reelId) {
      selectedReel.value = { ...selectedReel.value, ...body }
    }
    return Boolean(body.video_url)
  } catch {
    return false
  }
}

async function toggleVideoPlayback() {
  if (videoBusy.value) return
  videoBusy.value = true
  try {
    if (!selectedReel.value?.video_url) {
      const ok = await refreshPlaybackUrl()
      if (!ok) {
        saveError.value = 'Видео пока недоступно — попробуйте чуть позже'
        return
      }
      await new Promise((r) => setTimeout(r, 50))
    }
    const el = detailVideo.value
    if (!el) return
    if (el.paused) {
      applyVideoAudio()
      try {
        await el.play()
      } catch {
        const ok = await refreshPlaybackUrl()
        if (!ok) {
          saveError.value = 'Не удалось воспроизвести видео'
          return
        }
        await new Promise((r) => setTimeout(r, 80))
        const retry = detailVideo.value
        if (retry) {
          applyVideoAudio()
          await retry.play().catch(() => {
            saveError.value = 'Не удалось воспроизвести видео'
          })
        }
      }
    } else {
      el.pause()
    }
  } finally {
    videoBusy.value = false
  }
}

function applyVideoAudio() {
  const el = detailVideo.value
  if (!el) return
  el.muted = videoMuted.value
  el.volume = Math.min(1, Math.max(0, videoVolume.value))
}

function toggleVideoMute() {
  if (videoMuted.value) {
    videoMuted.value = false
    if (videoVolume.value <= 0.01) videoVolume.value = 0.7
  } else {
    videoMuted.value = true
  }
  applyVideoAudio()
}

function onVideoVolumeInput(event) {
  const next = Number(event?.target?.value)
  videoVolume.value = Number.isFinite(next) ? Math.min(1, Math.max(0, next)) : 0.7
  videoMuted.value = videoVolume.value <= 0.01
  applyVideoAudio()
}

function posterLine(reel) {
  const raw = (reel?.overlay_text || reel?.title || '').replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  return raw.length > 52 ? `${raw.slice(0, 51)}…` : raw
}

function onThumbError(event) {
  const img = event?.target
  if (!img) return
  img.style.display = 'none'
  const poster = img.closest('.poster, .compact-poster, .featured-video')
  if (poster) poster.classList.add('thumb-missing')
}

async function bootstrapAuth() {
  authBooting.value = true
  try {
    const me = await fetchMe()
    if (me) {
      currentUser.value = me
    } else if (!currentUser.value && appPages.includes(currentPage.value)) {
      currentPage.value = 'login'
      if (window.location.hash.replace(/^#/, '') !== 'login') {
        window.location.hash = 'login'
      }
    }
  } finally {
    authBooting.value = false
  }
}

async function onAuthEntered() {
  const me = await fetchMe()
  currentUser.value = me
  navigate('home')
}

async function onLogout() {
  await logoutAccount()
  currentUser.value = null
  competitorsList.value = []
  competitor.value = null
  competitorReels.value = []
  homeReels.value = []
  planItems.value = []
  navigate('landing')
}

function navigate(page, id = null) {
  if (appPages.includes(page) && !currentUser.value && !authBooting.value) {
    currentPage.value = 'login'
    if (window.location.hash.replace(/^#/, '') !== 'login') {
      window.location.hash = 'login'
    }
    return
  }
  currentPage.value = page
  let nextHash = page
  if (page === 'detail' && id) nextHash = `detail/${id}`
  if (page === 'competitors' && id) nextHash = `competitors/${id}`
  if (window.location.hash.replace(/^#/, '') !== nextHash) {
    window.location.hash = nextHash
  }
  if (marketingPages.includes(page)) {
    stopSpeechPolling()
    resetVideoUi()
    selectedReel.value = null
    editingSection.value = null
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  if (page === 'home') {
    stopSpeechPolling()
    resetVideoUi()
    selectedReel.value = null
    editingSection.value = null
    selectedCompetitorId.value = null
    remixMode.value = false
    remixMessage.value = ''
    void loadHomeReels()
  }
  if (page === 'plan') {
    stopSpeechPolling()
    resetVideoUi()
    selectedReel.value = null
    editingSection.value = null
    selectedCompetitorId.value = null
    remixMode.value = false
    void loadContentPlan()
  }
  if (page === 'competitors' && !id) {
    selectedCompetitorId.value = null
    competitor.value = null
    competitorReels.value = []
  }
  if (page === 'detail') {
    selectedCompetitorId.value = null
  }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function stopSpeechPolling() {
  speechPolling.value = false
  if (speechPollTimer) {
    window.clearInterval(speechPollTimer)
    speechPollTimer = null
  }
}

function applyAnalysisUpdate(body, reelId) {
  if (selectedReel.value?.id !== reelId) return
  const wasBusy = Boolean(
    selectedReel.value?.speech_pending ||
      selectedReel.value?.analysis_pending ||
      speechPolling.value,
  )
  selectedReel.value = body
  const stillBusy = Boolean(body.speech_pending || body.analysis_pending)
  if (wasBusy && !stillBusy) {
    analysisRevealKey.value += 1
    stopSpeechPolling()
  }
}

function startSpeechPolling(reelId) {
  stopSpeechPolling()
  speechPolling.value = true
  let attempts = 0
  const pollOnce = async () => {
    attempts += 1
    if (attempts > 50 || currentPage.value !== 'detail' || selectedReel.value?.id !== reelId) {
      stopSpeechPolling()
      return
    }
    try {
      const response = await fetch(`/api/reels/${reelId}`, { cache: 'no-store' })
      if (!response.ok) return
      const body = await response.json()
      applyAnalysisUpdate(body, reelId)
    } catch {
      // Keep the skeleton until the next poll succeeds.
    }
  }
  // First check quickly, then every 1.2s so finished analysis appears sooner.
  void pollOnce()
  speechPollTimer = window.setInterval(pollOnce, 1200)
}

async function copySection(section) {
  const reel = selectedReel.value
  if (!reel) return
  const value = remixMode.value
    ? reel?.[section] || ''
    : reel?.[`original_${section}`] || reel?.[section] || ''
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copiedSection.value = section
    if (copiedTimer) window.clearTimeout(copiedTimer)
    copiedTimer = window.setTimeout(() => {
      if (copiedSection.value === section) copiedSection.value = ''
    }, 1600)
  } catch {
    saveError.value = 'Не удалось скопировать текст'
  }
}

async function loadHomeReels() {
  const hadItems = homeReels.value.length > 0
  if (!hadItems) homeLoading.value = true
  try {
    const response = await fetch('/api/reels?limit=40', { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось загрузить рилсы')
    homeReels.value = await response.json()
  } catch (error) {
    saveError.value = error.message
  } finally {
    homeLoading.value = false
  }
}

async function openReel(reelId, { syncHash = true, remix = false } = {}) {
  if (!reelId) return
  detailLoading.value = true
  saveError.value = ''
  editingSection.value = null
  copiedSection.value = ''
  remixMode.value = remix
  remixMessage.value = ''
  resetVideoUi()
  stopSpeechPolling()
  analysisRevealKey.value += 1
  if (syncHash) {
    navigate('detail', reelId)
  } else {
    currentPage.value = 'detail'
  }

  try {
    const response = await fetch(`/api/reels/${reelId}`, { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось открыть рилс')
    selectedReel.value = await response.json()
    if (selectedReel.value?.speech_pending || selectedReel.value?.analysis_pending) {
      startSpeechPolling(reelId)
    } else {
      analysisRevealKey.value += 1
    }
    // Soft-refresh CDN video in background when missing.
    if (!selectedReel.value?.video_url) {
      void refreshPlaybackUrl()
    }
  } catch (error) {
    saveError.value = error.message
    selectedReel.value = null
  } finally {
    detailLoading.value = false
  }
}

async function startRemix(reelId) {
  if (!reelId || remixLoading.value) return
  await openReel(reelId, { remix: true })
  if (!selectedReel.value || selectedReel.value.id !== reelId) return

  remixLoading.value = true
  remixMessage.value = 'Готовим русский сценарий: перевод и разбивка на хук / скрипт / CTA…'
  saveError.value = ''
  // Clear stale RU fields so the UI doesn't flash old translation → new one.
  selectedReel.value = {
    ...selectedReel.value,
    hook: '',
    script: '',
    cta: '',
  }
  try {
    const response = await fetch(`/api/reels/${reelId}/remix`, { method: 'POST' })
    const body = await response.json()
    if (!response.ok) {
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg || item).join('; ')
        : body.detail
      throw new Error(detail || 'Не удалось подготовить Remix')
    }
    selectedReel.value = body
    analysisRevealKey.value += 1
    remixMessage.value =
      'Перевод готов. Сверьте с оригиналом, поправьте текст и утвердите в контент-план.'
    stopSpeechPolling()
  } catch (error) {
    saveError.value = error.message
    remixMessage.value = ''
  } finally {
    remixLoading.value = false
  }
}

async function approveRemixToPlan() {
  if (!selectedReel.value?.id) return
  if (selectedInPlan.value) {
    navigate('plan')
    return
  }
  const entry = await addToContentPlan(selectedReel.value.id)
  if (entry) {
    remixMessage.value = 'Сценарий утверждён и добавлен в контент-план'
    navigate('plan')
  }
}

async function loadInitialCompetitor() {
  await loadCompetitorsList()
  if (initialRoute.page === 'competitors' && initialRoute.competitorId) {
    await openCompetitor(initialRoute.competitorId, { syncHash: false })
  }
}

async function loadCompetitor(forceRefresh = false) {
  competitorLoading.value = true
  competitorMessage.value = 'Загружаем профиль и рилсы…'
  saveError.value = ''

  try {
    const response = await fetch('/api/competitors/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: competitorHandle.value,
        force_refresh: forceRefresh,
      }),
    })
    const body = await response.json()
    if (!response.ok) {
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg || item).join('; ')
        : body.detail
      throw new Error(detail || 'Не удалось загрузить конкурента')
    }

    competitorHandle.value = ''
    competitorMessage.value = body.message || 'Конкурент сохранён в списке'
    await loadCompetitorsList()
    // Stay on the list — user opens reels via «Открыть».
    selectedCompetitorId.value = null
    competitor.value = null
    competitorReels.value = []
  } catch (error) {
    saveError.value = error.message
    competitorMessage.value = ''
  } finally {
    competitorLoading.value = false
  }
}

function startEditing(section) {
  if (!selectedReel.value) return
  editingSection.value = section
  draft.value = selectedReel.value[section] || ''
  saveState.value = 'idle'
  saveError.value = ''
}

function cancelEditing() {
  editingSection.value = null
  draft.value = ''
  saveError.value = ''
}

async function saveSection(section) {
  if (!selectedReel.value || saveState.value === 'saving') return

  saveState.value = 'saving'
  saveError.value = ''

  try {
    const response = await fetch(`/api/reels/${selectedReel.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section, value: draft.value }),
    })
    const body = await response.json()

    if (!response.ok) {
      if (response.status === 403) {
        throw new Error('Редактирование разрешено только с вашего доверенного IP')
      }
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg || item).join('; ')
        : body.detail
      throw new Error(detail || 'Не удалось сохранить изменения')
    }

    selectedReel.value = body
    editingSection.value = null
    draft.value = ''
    saveState.value = 'saved'
    window.setTimeout(() => {
      if (saveState.value === 'saved') saveState.value = 'idle'
    }, 2200)
  } catch (error) {
    saveState.value = 'error'
    saveError.value = error.message
  }
}

function syncPageFromHash() {
  const { page, reelId, competitorId } = parseLocationHash()
  if (appPages.includes(page) && !currentUser.value && !authBooting.value) {
    currentPage.value = 'login'
    if (window.location.hash.replace(/^#/, '') !== 'login') {
      window.location.hash = 'login'
    }
    return
  }
  currentPage.value = page
  if (marketingPages.includes(page)) {
    stopSpeechPolling()
    selectedReel.value = null
    editingSection.value = null
    return
  }
  if (page === 'detail' && reelId) {
    if (selectedReel.value?.id !== reelId && !detailLoading.value) {
      openReel(reelId, { syncHash: false })
    }
    return
  }
  if (page === 'competitors') {
    selectedCompetitorId.value = competitorId
    if (competitorId) {
      if (competitor.value?.id !== competitorId && !competitorOpening.value) {
        openCompetitor(competitorId, { syncHash: false })
      }
    } else {
      competitor.value = null
      competitorReels.value = []
      void loadCompetitorsList()
    }
    return
  }
  if (page === 'plan') {
    stopSpeechPolling()
    selectedReel.value = null
    editingSection.value = null
    selectedCompetitorId.value = null
    void loadContentPlan()
    return
  }
  stopSpeechPolling()
  selectedReel.value = null
  editingSection.value = null
  selectedCompetitorId.value = null
}

async function loadCompetitorsList() {
  try {
    const response = await fetch('/api/competitors', { cache: 'no-store' })
    if (!response.ok) return
    competitorsList.value = await response.json()
  } catch {
    // Keep the last known list if refresh fails.
  }
}

async function openCompetitor(competitorId, { syncHash = true } = {}) {
  if (!competitorId) return
  competitorOpening.value = true
  competitorAvatarBroken.value = false
  saveError.value = ''
  selectedCompetitorId.value = competitorId
  if (syncHash) navigate('competitors', competitorId)
  else currentPage.value = 'competitors'

  try {
    const [profileResponse, reelsResponse] = await Promise.all([
      fetch(`/api/competitors/${competitorId}`, { cache: 'no-store' }),
      fetch(`/api/competitors/${competitorId}/reels`, { cache: 'no-store' }),
    ])
    if (!profileResponse.ok) throw new Error('Не удалось открыть конкурента')
    competitor.value = await profileResponse.json()
    competitorReels.value = reelsResponse.ok ? await reelsResponse.json() : []
    competitorMessage.value = `Показаны ${competitorReels.value.length} рилсов`
  } catch (error) {
    saveError.value = error.message
    competitor.value = null
    competitorReels.value = []
  } finally {
    competitorOpening.value = false
  }
}

function backToCompetitorsList() {
  navigate('competitors')
  void loadCompetitorsList()
}

function onListAvatarError(competitorId) {
  competitorListAvatarBroken.value = {
    ...competitorListAvatarBroken.value,
    [competitorId]: true,
  }
}

async function loadContentPlan() {
  planLoading.value = true
  try {
    const response = await fetch('/api/content-plan', { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось загрузить контент-план')
    planItems.value = await response.json()
  } catch (error) {
    saveError.value = error.message
  } finally {
    planLoading.value = false
  }
}

function isPlanExpanded(itemId) {
  return Boolean(expandedPlanIds.value[itemId])
}

function togglePlanExpanded(itemId) {
  expandedPlanIds.value = {
    ...expandedPlanIds.value,
    [itemId]: !expandedPlanIds.value[itemId],
  }
}

async function removeFromContentPlan(item) {
  if (!item?.id || planBusyItemId.value === item.id) return
  planBusyItemId.value = item.id
  planMessage.value = ''
  saveError.value = ''
  try {
    const response = await fetch(`/api/content-plan/${item.id}`, { method: 'DELETE' })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || 'Не удалось удалить из плана')
    }
    planItems.value = planItems.value.filter((row) => row.id !== item.id)
    const nextExpanded = { ...expandedPlanIds.value }
    delete nextExpanded[item.id]
    expandedPlanIds.value = nextExpanded
    syncReelPlanFields(item.reel_id, null)
    planMessage.value = 'Удалено из контент-плана'
  } catch (error) {
    saveError.value = error.message
  } finally {
    planBusyItemId.value = null
  }
}

async function addToContentPlan(reelId) {
  if (!reelId || planBusyReelId.value === reelId) return
  const existing = planEntryForReel(reelId)
  if (existing) {
    planMessage.value = 'Уже в контент-плане'
    return existing
  }
  planBusyReelId.value = reelId
  planMessage.value = ''
  saveError.value = ''
  try {
    const response = await fetch('/api/content-plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reel_id: reelId }),
    })
    const body = await response.json()
    if (!response.ok) {
      const detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg || item).join('; ')
        : body.detail
      throw new Error(detail || 'Не удалось добавить в контент-план')
    }
    planItems.value = [body, ...planItems.value.filter((item) => item.id !== body.id)]
    syncReelPlanFields(reelId, body)
    planMessage.value = 'Добавлено в контент-план'
    return body
  } catch (error) {
    saveError.value = error.message
    return null
  } finally {
    planBusyReelId.value = null
  }
}

async function setShootStatus(itemId, shootStatus) {
  const current = planItems.value.find((item) => item.id === itemId)
  const previous = current?.shoot_status
  if (current) {
    if (current.shoot_status === shootStatus) return
    current.shoot_status = shootStatus
  }
  try {
    const response = await fetch(`/api/content-plan/${itemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shoot_status: shootStatus }),
    })
    const body = await response.json()
    if (!response.ok) {
      throw new Error(body.detail || 'Не удалось обновить статус')
    }
    if (planItems.value.some((item) => item.id === itemId)) {
      planItems.value = planItems.value.map((item) => (item.id === itemId ? body : item))
    } else {
      planItems.value = [body, ...planItems.value]
    }
    syncReelPlanFields(body.reel_id, body)
  } catch (error) {
    if (current) current.shoot_status = previous
    saveError.value = error.message
  }
}

async function setShootStatusForReel(reelId, shootStatus) {
  let entry = planEntryForReel(reelId)
  if (!entry) {
    const reel = [...homeReels.value, ...competitorReels.value].find((item) => item.id === reelId)
    if (reel?.plan_item_id) {
      entry = { id: reel.plan_item_id, shoot_status: reel.shoot_status, reel_id: reelId }
    } else {
      entry = await addToContentPlan(reelId)
    }
  }
  if (!entry) return
  await setShootStatus(entry.id, shootStatus)
}

onMounted(async () => {
  window.addEventListener('hashchange', syncPageFromHash)
  const bootQuery = new URLSearchParams(window.location.search)
  const oauthError = bootQuery.get('oauth_error')
  if (oauthError) {
    try {
      sessionStorage.setItem('reelsai_oauth_error', oauthError)
    } catch {
      // ignore
    }
  }
  if (bootQuery.get('auth') === 'verify-otp' || bootQuery.get('auth') === 'home' || oauthError) {
    const cleanHash =
      bootQuery.get('auth') === 'home'
        ? 'home'
        : bootQuery.get('auth') === 'verify-otp'
          ? 'verify-otp'
          : 'login'
    window.history.replaceState({}, '', `${window.location.pathname}#${cleanHash}`)
    currentPage.value = cleanHash
  }
  const oauthTicket = bootQuery.get('ticket')
  if (oauthTicket) {
    try {
      const claimed = await claimOauthTicket(oauthTicket)
      currentUser.value = claimed.user
      clearChallenge()
    } catch (err) {
      try {
        sessionStorage.setItem(
          'reelsai_oauth_error',
          err.message || 'Не удалось завершить вход через OAuth',
        )
      } catch {
        // ignore
      }
      currentPage.value = 'login'
      window.location.hash = 'login'
      authBooting.value = false
      return
    }
  }
  await bootstrapAuth()
  if (bootQuery.get('auth') === 'home' && currentUser.value) {
    void loadHomeReels()
    void loadInitialCompetitor()
    void loadContentPlan()
    return
  }
  if (bootQuery.get('auth') === 'home' && !currentUser.value) {
    currentPage.value = 'login'
    window.location.hash = 'login'
    try {
      sessionStorage.setItem('reelsai_oauth_error', 'Сессия после OAuth не сохранилась, попробуйте ещё раз')
    } catch {
      // ignore
    }
    authBooting.value = false
    return
  }
  if (marketingPages.includes(initialRoute.page) || marketingPages.includes(currentPage.value)) {
    if (!window.location.hash || window.location.hash === '#') {
      window.location.hash = currentPage.value === 'landing' ? 'landing' : currentPage.value
    }
    return
  }
  if (!currentUser.value) {
    navigate('login')
    return
  }
  void loadContentPlan()
  if (initialRoute.page === 'detail' && initialRoute.reelId) {
    // Open the reel immediately — home discovery can take tens of seconds.
    await openReel(initialRoute.reelId, { syncHash: false })
    void Promise.all([loadHomeReels(), loadInitialCompetitor()])
    return
  }
  if (initialRoute.page === 'plan') {
    await Promise.all([loadContentPlan(), loadHomeReels(), loadInitialCompetitor()])
    return
  }
  await Promise.all([loadHomeReels(), loadInitialCompetitor()])
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncPageFromHash)
  stopSpeechPolling()
  if (copiedTimer) window.clearTimeout(copiedTimer)
  clearChromeIdleTimer()
})
</script>

<template>
  <div v-if="authBooting" class="mkt-shell mkt-auth" style="min-height: 100vh">
    <div class="mkt-auth-card" style="text-align: center">
      <LoaderCircle :size="28" class="spin" />
      <p style="margin: 12px 0 0; color: #6b6680">Загрузка…</p>
    </div>
  </div>
  <LandingPage
    v-else-if="currentPage === 'landing'"
    @navigate="navigate"
  />
  <LoginPage
    v-else-if="currentPage === 'login'"
    @navigate="navigate"
  />
  <RegisterPage
    v-else-if="currentPage === 'register'"
    @navigate="navigate"
  />
  <VerifyOtpPage
    v-else-if="currentPage === 'verify-otp'"
    @navigate="navigate"
    @entered="onAuthEntered"
  />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <button class="brand" type="button" @click="navigate('home')">
        <span class="brand-mark"><WandSparkles :size="19" /></span>
        <span>Reels<br />Finder</span>
      </button>

      <nav class="primary-nav" aria-label="Основная навигация">
        <button
          class="nav-item"
          :class="{ active: currentPage === 'home' }"
          type="button"
          @click="navigate('home')"
        >
          <Home :size="18" />
          <span>Главное</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: currentPage === 'plan' }"
          type="button"
          @click="navigate('plan')"
        >
          <ClipboardList :size="18" />
          <span>Контент план</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: currentPage === 'competitors' }"
          type="button"
          @click="navigate('competitors')"
        >
          <Users :size="18" />
          <span>Конкуренты</span>
        </button>
      </nav>
      <div v-if="currentUser" class="sidebar-user">
        <span class="sidebar-user-avatar" aria-hidden="true">
          <UserRound :size="16" />
        </span>
        <div class="sidebar-user-meta">
          <strong>{{ userLabel }}</strong>
          <span v-if="currentUser.name && userEmail">{{ userEmail }}</span>
        </div>
      </div>
      <button
        class="nav-item"
        type="button"
        @click="onLogout"
      >
        <X :size="18" />
        <span>Выйти</span>
      </button>
    </aside>

    <main class="workspace">
      <section v-if="currentPage === 'home'" class="page home-page">
        <header class="page-header home-header">
          <div>
            <span class="eyebrow">Рилсы ваших конкурентов</span>
            <h1>Главное</h1>
            <p>Лента рилсов из сохранённых конкурентов — без случайных аккаунтов.</p>
          </div>
          <label class="search-field">
            <Search :size="17" />
            <input
              v-model="searchQuery"
              type="search"
              placeholder="Поиск по хукам, темам, авторам..."
            />
            <kbd>⌘ K</kbd>
          </label>
        </header>

        <div class="section-heading">
          <div>
            <span class="live-dot"></span>
            <strong>Из конкурентов</strong>
          </div>
          <span>{{ homeLoading ? 'Загрузка...' : `Найдено ${filteredReels.length}` }}</span>
        </div>

        <div v-if="filteredReels.length" class="home-feed">
          <article v-for="reel in filteredReels" :key="reel.id" class="home-feed-row">
            <button class="home-feed-thumb" type="button" @click="openReel(reel.id)">
              <img
                v-if="reel.thumbnail_url"
                :src="thumbSrc(reel.thumbnail_url)"
                :alt="reel.title"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="onThumbError"
              />
              <span class="duration"><Play :size="9" fill="currentColor" /> {{ reel.duration }}</span>
            </button>
            <div class="home-feed-body">
              <button class="home-feed-title" type="button" @click="openReel(reel.id)">
                {{ reel.title }}
              </button>
              <div class="home-feed-tags">
                <span>Instagram</span>
                <span>Reels</span>
              </div>
              <div class="home-feed-meta">
                <span><Eye :size="12" /> {{ formatViews(reel.views_count) }}</span>
                <span><Heart :size="12" /> {{ formatViews(reel.likes_count) }}</span>
                <span>{{ reel.author }}</span>
                <span v-if="formatPostedAt(reel.posted_at)">{{ formatPostedAt(reel.posted_at) }}</span>
              </div>
            </div>
            <div class="home-feed-actions">
              <button class="ghost-button remix-chip" type="button" @click="startRemix(reel.id)">
                <WandSparkles :size="14" />
                Remix
              </button>
              <button
                v-if="!(reel.in_plan || planEntryForReel(reel.id))"
                class="ghost-button plan-chip"
                type="button"
                :disabled="planBusyReelId === reel.id"
                @click="addToContentPlan(reel.id)"
              >
                + В план
              </button>
              <span
                v-else
                class="status-chip readonly"
                :class="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status || 'todo')"
                :title="shootStatusLabel(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status)"
              >
                <CircleX
                  v-if="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) === 'todo'"
                  :size="13"
                />
                <Timer
                  v-else-if="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) === 'ready'"
                  :size="13"
                />
                <CircleCheck v-else :size="13" />
                {{ shootStatusLabel(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) }}
              </span>
            </div>
          </article>
        </div>

        <div v-else class="empty-state">
          <Users :size="30" />
          <strong>{{ homeLoading ? 'Загружаем рилсы...' : 'Пока нет рилсов конкурентов' }}</strong>
          <span>Добавьте конкурента и загрузите его рилсы — они появятся здесь</span>
        </div>
      </section>

      <section v-else-if="currentPage === 'plan'" class="page plan-page">
        <header class="page-header">
          <div>
            <h1>Контент план</h1>
            <p>Русские сценарии, которые берём в работу и доводим до съёмки</p>
          </div>
        </header>

        <div v-if="planMessage" class="competitor-feedback">
          <span class="success-badge"><Check :size="14" /> {{ planMessage }}</span>
        </div>

        <div v-if="planItems.length" class="plan-cards">
          <article
            v-for="item in planItems"
            :key="item.id"
            class="plan-card"
            :class="{ expanded: isPlanExpanded(item.id) }"
          >
            <div class="plan-card-top">
              <button class="plan-card-thumb" type="button" @click="openReel(item.reel_id)">
                <img
                  v-if="item.thumbnail_url"
                  :src="thumbSrc(item.thumbnail_url)"
                  :alt="item.title"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                  @error="onThumbError"
                />
                <span class="duration"><Play :size="9" fill="currentColor" /> {{ item.duration }}</span>
              </button>
              <div class="plan-card-heading">
                <strong>{{ item.title }}</strong>
                <span>{{ item.author }}<template v-if="formatPostedAt(item.posted_at)"> · {{ formatPostedAt(item.posted_at) }}</template></span>
                <div class="status-chip compact" :class="item.shoot_status">
                  <CircleX v-if="item.shoot_status === 'todo'" :size="12" />
                  <Timer v-else-if="item.shoot_status === 'ready'" :size="12" />
                  <CircleCheck v-else :size="12" />
                  {{ shootStatusLabel(item.shoot_status) }}
                </div>
              </div>
              <div class="plan-card-controls">
                <div class="plan-status-group" role="group" aria-label="Статус съёмки">
                  <button
                    type="button"
                    class="plan-status-btn todo"
                    :class="{ active: item.shoot_status === 'todo' }"
                    title="Не взят в работу"
                    aria-label="Не взят в работу"
                    @click="setShootStatus(item.id, 'todo')"
                  >
                    <CircleX :size="15" :stroke-width="2.25" />
                  </button>
                  <button
                    type="button"
                    class="plan-status-btn ready"
                    :class="{ active: item.shoot_status === 'ready' }"
                    title="Ждёт съёмки"
                    aria-label="Ждёт съёмки"
                    @click="setShootStatus(item.id, 'ready')"
                  >
                    <Timer :size="15" :stroke-width="2.25" />
                  </button>
                  <button
                    type="button"
                    class="plan-status-btn done"
                    :class="{ active: item.shoot_status === 'done' }"
                    title="Снят и выложен"
                    aria-label="Снят и выложен"
                    @click="setShootStatus(item.id, 'done')"
                  >
                    <CircleCheck :size="15" :stroke-width="2.25" />
                  </button>
                </div>
                <button
                  class="icon-button plan-remove-button"
                  type="button"
                  title="Удалить из плана"
                  aria-label="Удалить из плана"
                  :disabled="planBusyItemId === item.id"
                  @click="removeFromContentPlan(item)"
                >
                  <Trash2 :size="15" />
                </button>
              </div>
            </div>

            <div class="plan-card-toolbar">
              <button
                class="ghost-button plan-expand-button"
                type="button"
                @click="togglePlanExpanded(item.id)"
              >
                <ChevronUp v-if="isPlanExpanded(item.id)" :size="15" />
                <ChevronDown v-else :size="15" />
                {{ isPlanExpanded(item.id) ? 'Свернуть карточку' : 'Развернуть карточку' }}
              </button>
              <button class="ghost-button" type="button" @click="openReel(item.reel_id)">
                Открыть карточку
              </button>
            </div>

            <div
              class="plan-card-details"
              :class="{ open: isPlanExpanded(item.id) }"
            >
              <div class="plan-card-details-inner">
                <div class="plan-script-block">
                  <span>ХУК</span>
                  <p>{{ item.hook || 'Хук ещё не готов — откройте карточку рилса' }}</p>
                </div>
                <div class="plan-script-block">
                  <span>СКРИПТ</span>
                  <p>{{ item.script || 'Скрипт ещё не готов — откройте карточку рилса' }}</p>
                </div>
                <div class="plan-script-block">
                  <span>CALL TO ACTION</span>
                  <p>{{ item.cta || 'CTA ещё не готов' }}</p>
                </div>

                <div class="plan-card-footer">
                  <a
                    v-if="item.instagram_url"
                    class="open-original-chip"
                    :href="item.instagram_url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ArrowUpRight :size="12" />
                    Оригинальный Reels
                  </a>
                </div>
              </div>
            </div>
          </article>
        </div>

        <div v-else class="empty-state">
          <Clapperboard :size="30" />
          <strong>{{ planLoading ? 'Загружаем план…' : 'Контент-план пуст' }}</strong>
          <span>Добавьте рилс с главной или из конкурентов кнопкой «+ В план»</span>
        </div>
      </section>

      <section v-else-if="currentPage === 'competitors'" class="page competitors-page">
        <header class="page-header">
          <div>
            <h1>Конкуренты</h1>
            <p>Анализируйте рилсы конкурентов и находите рабочие механики</p>
          </div>
        </header>

        <template v-if="!selectedCompetitorId">
          <div class="competitors-list-view">
          <div class="competitor-loader">
            <span class="competitor-loader-label">Instagram аккаунт или URL</span>
            <label class="competitor-loader-field">
              <Camera :size="18" />
              <input
                v-model="competitorHandle"
                type="text"
                placeholder="@username"
                aria-label="Instagram аккаунт или URL"
                autocomplete="off"
                spellcheck="false"
                @keydown.enter.prevent="loadCompetitor(false)"
              />
            </label>
            <button
              class="primary-button competitor-loader-submit"
              type="button"
              :disabled="competitorLoading || !competitorHandle.trim()"
              @click="loadCompetitor(false)"
            >
              {{ competitorLoading ? 'Загружаем…' : 'Загрузить 20 рилсов' }}
              <ArrowUpRight :size="17" />
            </button>
          </div>

          <div v-if="competitorMessage || saveError" class="competitor-feedback">
            <span v-if="competitorMessage" class="success-badge"><Check :size="14" /> {{ competitorMessage }}</span>
            <span v-if="saveError" class="save-notice error"><CircleHelp :size="14" /> {{ saveError }}</span>
          </div>

          <div class="competitors-section">
            <h2>Загруженные конкуренты</h2>

            <div v-if="competitorsList.length" class="competitors-list">
              <article
                v-for="item in competitorsList"
                :key="item.id"
                class="competitor-row"
              >
                <div class="competitor-row-main">
                  <img
                    v-if="item.avatar_url && !competitorListAvatarBroken[item.id]"
                    class="profile-avatar competitor-row-avatar"
                    :src="thumbSrc(item.avatar_url)"
                    :alt="item.full_name || item.username"
                    referrerpolicy="no-referrer"
                    @error="onListAvatarError(item.id)"
                  />
                  <span v-else class="profile-avatar competitor-row-avatar profile-avatar-fallback" aria-hidden="true">
                    {{ competitorInitial(item) }}
                  </span>
                  <div class="competitor-row-meta">
                    <strong>@{{ item.username }}</strong>
                    <span>Загружено рилсов: {{ item.reels_count ?? 0 }}</span>
                  </div>
                </div>
                <div class="competitor-row-aside">
                  <time class="competitor-row-time">{{ formatRelativeTime(item.last_scraped_at || item.updated_at) }}</time>
                  <button
                    class="ghost-button competitor-open-button"
                    type="button"
                    @click="openCompetitor(item.id)"
                  >
                    Открыть
                  </button>
                </div>
              </article>
            </div>

            <div v-else class="empty-state competitors-empty">
              <Users :size="30" />
              <strong>Список конкурентов пуст</strong>
              <span>Введите @username выше и загрузите 20 рилсов</span>
            </div>
          </div>
          </div>
        </template>

        <template v-else>
          <button class="back-button" type="button" @click="backToCompetitorsList">
            <ArrowLeft :size="17" />
            К списку конкурентов
          </button>

          <div v-if="competitorOpening || !competitor" class="empty-state detail-boot">
            <LoaderCircle :size="28" class="spin" />
            <strong>{{ competitorOpening ? 'Открываем рилсы…' : (saveError || 'Конкурент не найден') }}</strong>
          </div>

          <template v-else>
            <article class="profile-card">
              <div class="profile-main">
                <img
                  v-if="competitor.avatar_url && !competitorAvatarBroken"
                  class="profile-avatar"
                  :src="thumbSrc(competitor.avatar_url)"
                  :alt="competitor.full_name || competitor.username"
                  referrerpolicy="no-referrer"
                  @error="onCompetitorAvatarError"
                />
                <span v-else class="profile-avatar profile-avatar-fallback" aria-hidden="true">
                  {{ competitorInitial(competitor) }}
                </span>
                <div>
                  <strong>{{ competitor.full_name || competitor.username }}</strong>
                  <span>@{{ competitor.username }}</span>
                  <p class="preserve-lines">{{ competitor.bio }}</p>
                </div>
              </div>
              <div class="profile-stats">
                <span><strong>{{ competitorReels.length }}</strong><small>рилсов</small></span>
                <span v-if="competitor.followers_count"><strong>{{ formatFollowers(competitor.followers_count) }}</strong><small>подписчики</small></span>
                <span v-if="competitor.following_count"><strong>{{ competitor.following_count }}</strong><small>подписки</small></span>
              </div>
            </article>

            <div class="results-heading">
              <div>
                <h2>{{ competitorReels.length }} рилсов</h2>
                <p>До 20 штук, отсортировано по просмотрам</p>
              </div>
              <span class="success-badge"><Check :size="14" /> Готово</span>
            </div>

            <div v-if="competitorReels.length" class="compact-reels-grid">
              <article
                v-for="reel in competitorReels"
                :key="reel.id"
                class="compact-reel"
              >
                <button class="compact-poster" type="button" @click="openReel(reel.id)">
                  <img
                    v-if="reel.thumbnail_url"
                    :src="thumbSrc(reel.thumbnail_url)"
                    :alt="reel.title"
                    loading="lazy"
                    referrerpolicy="no-referrer"
                    @error="onThumbError"
                  />
                  <span class="duration"><Play :size="9" fill="currentColor" /> {{ reel.duration }}</span>
                </button>
                <button class="compact-title" type="button" @click="openReel(reel.id)">
                  <strong>{{ reel.title }}</strong>
                </button>
                <div class="compact-stats">
                  <span>{{ formatViews(reel.views_count) }} views</span>
                  <span>{{ formatViews(reel.likes_count) }} likes</span>
                </div>
                <div class="compact-plan-row">
                  <button
                    v-if="!(reel.in_plan || planEntryForReel(reel.id))"
                    class="ghost-button plan-chip compact-plan-chip"
                    type="button"
                    :disabled="planBusyReelId === reel.id"
                    @click.stop="addToContentPlan(reel.id)"
                  >
                    + В план
                  </button>
                  <span
                    v-else
                    class="status-chip compact-status-chip readonly"
                    :class="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status || 'todo')"
                    :title="shootStatusLabel(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status)"
                  >
                    <CircleX
                      v-if="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) === 'todo'"
                      :size="12"
                    />
                    <Timer
                      v-else-if="(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) === 'ready'"
                      :size="12"
                    />
                    <CircleCheck v-else :size="12" />
                    {{ shootStatusLabel(planEntryForReel(reel.id)?.shoot_status || reel.shoot_status) }}
                  </span>
                </div>
              </article>
            </div>

            <div v-else class="empty-state">
              <Search :size="30" />
              <strong>Рилсов пока нет</strong>
              <span>Попробуйте добавить аккаунт ещё раз</span>
            </div>
          </template>
        </template>
      </section>

      <section v-else class="page detail-page">
        <button class="back-button" type="button" @click="navigate('home')">
          <ArrowLeft :size="17" />
          Назад к списку
        </button>

        <div v-if="detailLoading || !selectedReel" class="empty-state detail-boot">
          <LoaderCircle :size="28" class="spin" />
          <strong>{{ detailLoading ? 'Открываем разбор…' : (saveError || 'Рилс не выбран') }}</strong>
          <p v-if="saveError && !detailLoading">Попробуйте открыть рилс снова с главной.</p>
        </div>

        <div v-else class="detail-layout">
          <div class="video-column">
            <div
              class="featured-video"
              :class="{
                playing: videoPlaying,
                'thumb-missing': !selectedReel.thumbnail_url,
                'show-chrome': showVideoChrome,
              }"
              @mouseenter="revealVideoChrome"
              @mousemove="revealVideoChrome"
              @mouseleave="hideVideoChrome"
            >
              <video
                v-if="playbackSrc"
                ref="detailVideo"
                class="detail-player"
                :src="playbackSrc"
                :poster="selectedReel.thumbnail_url ? thumbSrc(selectedReel.thumbnail_url) : undefined"
                playsinline
                loop
                preload="metadata"
                @timeupdate="onVideoTimeUpdate"
                @play="onVideoPlay"
                @pause="onVideoPause"
                @click="toggleVideoPlayback"
              ></video>
              <img
                v-else-if="selectedReel.thumbnail_url"
                :src="thumbSrc(selectedReel.thumbnail_url)"
                :alt="selectedReel.title"
                referrerpolicy="no-referrer"
                @error="onThumbError"
              />
              <span v-if="!videoPlaying" class="poster-shade"></span>
              <span v-if="!videoPlaying" class="poster-hook">{{ posterLine(selectedReel) }}</span>
              <div class="video-chrome">
                <button
                  v-if="!videoPlaying"
                  type="button"
                  class="video-play-btn"
                  aria-label="Воспроизвести видео"
                  :disabled="videoBusy"
                  @click="toggleVideoPlayback"
                >
                  <LoaderCircle v-if="videoBusy" :size="22" class="spin" />
                  <Play v-else :size="24" fill="currentColor" />
                </button>
                <div v-if="playbackSrc" class="video-volume" @click.stop>
                  <button
                    type="button"
                    class="video-mute-btn"
                    :aria-label="videoMuted || videoVolume <= 0.01 ? 'Включить звук' : 'Выключить звук'"
                    @click="toggleVideoMute"
                  >
                    <VolumeX v-if="videoMuted || videoVolume <= 0.01" :size="15" />
                    <Volume2 v-else :size="15" />
                  </button>
                  <input
                    class="video-volume-slider"
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    :value="videoMuted ? 0 : videoVolume"
                    aria-label="Громкость"
                    @input="onVideoVolumeInput"
                  />
                </div>
                <span class="video-progress"><i :style="{ width: `${videoProgressPct}%` }"></i></span>
                <span class="video-time">{{ videoCurrentLabel }} / {{ selectedDurationLabel }}</span>
              </div>
            </div>
            <div class="video-actions single">
              <button
                v-if="remixMode"
                class="primary-button wide"
                type="button"
                :disabled="planBusyReelId === selectedReel.id || remixLoading"
                @click="approveRemixToPlan"
              >
                <Clapperboard :size="17" />
                {{ selectedInPlan ? 'Уже в плане — открыть' : 'Утвердить в контент-план' }}
              </button>
              <button
                v-else
                class="primary-button wide"
                type="button"
                :disabled="remixLoading"
                @click="startRemix(selectedReel.id)"
              >
                <WandSparkles :size="17" />
                {{ remixLoading ? 'Готовим Remix…' : 'Сделать Remix' }}
              </button>
            </div>
          </div>

          <div class="analysis-column">
            <header class="detail-title">
              <div>
                <span class="eyebrow">{{ remixMode ? 'Remix · адаптация под съёмку' : 'AI-разбор' }}</span>
                <h1>{{ selectedReel.title }}</h1>
                <p v-if="remixMode" class="detail-remix-lead">
                  Hook → Script → CTA · оригинал и перевод · правки → контент-план
                </p>
              </div>
            </header>

            <div class="creator-row">
              <span class="creator-avatar">{{ (selectedReel.author_name || selectedReel.author || 'A').slice(0, 1).toUpperCase() }}</span>
              <span class="creator-source">
                <strong>{{ selectedReel.author_name || selectedReel.author }}</strong>
                <small>Источник · {{ selectedReel.author }}</small>
              </span>
              <a
                v-if="selectedReel.instagram_url"
                class="instagram-button primary-original"
                :href="selectedReel.instagram_url"
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink :size="15" />
                Открыть оригинал
                <ArrowUpRight :size="14" />
              </a>
            </div>

            <div class="detail-stats">
              <span class="stat-pill views"><Eye :size="15" /> <strong>{{ selectedViewsLabel }}</strong> просмотров</span>
              <span class="stat-pill likes"><Heart :size="15" /> <strong>{{ formatViews(selectedReel.likes_count) }}</strong> лайков</span>
              <span class="stat-pill comments"><MessageCircle :size="15" /> <strong>{{ formatViews(selectedReel.comments_count) }}</strong> комм.</span>
            </div>

            <div class="insight-list">
              <div v-if="remixMessage" class="save-notice success">
                <WandSparkles :size="15" />
                {{ remixMessage }}
              </div>
              <div v-if="remixLoading" class="save-notice success">
                <LoaderCircle :size="15" class="spin" />
                Переводим оригинал на русский…
              </div>
              <div v-if="saveState === 'saved'" class="save-notice success">
                <Check :size="15" />
                Изменения сохранены
              </div>
              <div v-if="saveError" class="save-notice error">
                <CircleHelp :size="15" />
                {{ saveError }}
              </div>

              <!-- Remix: Hook → Script → CTA, оригинал | перевод (1:1) -->
              <template v-if="remixMode">
                <article class="insight-card bilingual-script-card hook-card">
                  <div class="insight-title">
                    <span class="insight-icon"><Zap :size="18" fill="currentColor" /></span>
                    <span>
                      <strong>Hook</strong>
                      <small>Оригинал и перевод · редактируйте правую колонку</small>
                    </span>
                    <div v-if="editingSection !== 'hook'" class="insight-actions">
                      <button type="button" @click="copySection('hook')">
                        <Copy :size="14" />
                        {{ copiedSection === 'hook' ? 'Скопировано' : 'Копировать' }}
                      </button>
                      <button type="button" @click="startEditing('hook')">
                        <Pencil :size="14" /> Редактировать
                      </button>
                    </div>
                  </div>
                  <div class="bilingual-grid">
                    <div class="bilingual-col">
                      <span class="bilingual-label">Оригинал</span>
                      <div class="bilingual-pane original-pane compact">
                        <p v-if="selectedReel.original_hook">{{ selectedReel.original_hook }}</p>
                        <p v-else-if="selectedReel.speech_pending" class="bilingual-empty">Расшифровываем речь…</p>
                        <p v-else class="bilingual-empty">Нет текста для хука</p>
                      </div>
                    </div>
                    <div class="bilingual-col">
                      <span class="bilingual-label">Перевод</span>
                      <div
                        class="bilingual-pane translation-pane compact"
                        :class="{ 'is-loading': remixLoading && editingSection !== 'hook' }"
                      >
                        <textarea
                          v-if="editingSection === 'hook'"
                          v-model="draft"
                          rows="4"
                          :maxlength="sectionLimits.hook"
                          autofocus
                          @keydown.ctrl.enter.prevent="saveSection('hook')"
                        ></textarea>
                        <div v-else-if="remixLoading" class="remix-skel" aria-hidden="true">
                          <span></span><span></span><span></span>
                        </div>
                        <p v-else-if="selectedReel.hook">{{ selectedReel.hook }}</p>
                        <p v-else class="bilingual-empty">Перевод появится после Remix</p>
                      </div>
                    </div>
                  </div>
                  <div v-if="editingSection === 'hook'" class="editor-actions bilingual-editor-actions">
                    <span>Ctrl + Enter, чтобы сохранить</span>
                    <button class="cancel-button" type="button" @click="cancelEditing">
                      <X :size="14" /> Отмена
                    </button>
                    <button
                      class="save-button"
                      type="button"
                      :disabled="saveState === 'saving' || !draft.trim()"
                      @click="saveSection('hook')"
                    >
                      <Save :size="14" />
                      {{ saveState === 'saving' ? 'Сохраняем...' : 'Сохранить' }}
                    </button>
                  </div>
                  <span class="counter">
                    {{ editingSection === 'hook' ? draft.length : (selectedReel.hook || '').length }}/{{ sectionLimits.hook }}
                  </span>
                </article>

                <article class="insight-card bilingual-script-card script-card">
                  <div class="insight-title">
                    <span class="insight-icon"><FileText :size="18" /></span>
                    <span>
                      <strong>Script</strong>
                      <small>Оригинал и перевод · редактируйте правую колонку</small>
                    </span>
                    <div v-if="editingSection !== 'script'" class="insight-actions">
                      <button type="button" @click="copySection('script')">
                        <Copy :size="14" />
                        {{ copiedSection === 'script' ? 'Скопировано' : 'Копировать' }}
                      </button>
                      <button type="button" @click="startEditing('script')">
                        <Pencil :size="14" /> Редактировать
                      </button>
                    </div>
                  </div>
                  <div class="bilingual-grid">
                    <div class="bilingual-col">
                      <span class="bilingual-label">Оригинал</span>
                      <div class="bilingual-pane original-pane script-pane">
                        <p v-if="selectedReel.original_script">{{ selectedReel.original_script }}</p>
                        <p v-else-if="selectedReel.speech_pending" class="bilingual-empty">Расшифровываем речь…</p>
                        <p v-else class="bilingual-empty">Нет текста для скрипта</p>
                      </div>
                    </div>
                    <div class="bilingual-col">
                      <span class="bilingual-label">Перевод</span>
                      <div
                        class="bilingual-pane translation-pane script-pane"
                        :class="{ 'is-loading': remixLoading && editingSection !== 'script' }"
                      >
                        <textarea
                          v-if="editingSection === 'script'"
                          v-model="draft"
                          rows="10"
                          :maxlength="sectionLimits.script"
                          autofocus
                          @keydown.ctrl.enter.prevent="saveSection('script')"
                        ></textarea>
                        <div v-else-if="remixLoading" class="remix-skel" aria-hidden="true">
                          <span></span><span></span><span></span>
                        </div>
                        <p v-else-if="scriptBody">{{ scriptBody }}</p>
                        <p v-else class="bilingual-empty">Перевод появится после Remix</p>
                      </div>
                    </div>
                  </div>
                  <div v-if="editingSection === 'script'" class="editor-actions bilingual-editor-actions">
                    <span>Ctrl + Enter, чтобы сохранить</span>
                    <button class="cancel-button" type="button" @click="cancelEditing">
                      <X :size="14" /> Отмена
                    </button>
                    <button
                      class="save-button"
                      type="button"
                      :disabled="saveState === 'saving' || !draft.trim()"
                      @click="saveSection('script')"
                    >
                      <Save :size="14" />
                      {{ saveState === 'saving' ? 'Сохраняем...' : 'Сохранить' }}
                    </button>
                  </div>
                  <span class="counter">
                    {{ editingSection === 'script' ? draft.length : scriptBody.length }}/{{ sectionLimits.script }}
                  </span>
                </article>

                <article class="insight-card bilingual-script-card cta-card">
                  <div class="insight-title">
                    <span class="insight-icon"><Target :size="18" /></span>
                    <span>
                      <strong>Call to Action</strong>
                      <small>Оригинал и перевод · редактируйте правую колонку</small>
                    </span>
                    <div v-if="editingSection !== 'cta'" class="insight-actions">
                      <button type="button" @click="copySection('cta')">
                        <Copy :size="14" />
                        {{ copiedSection === 'cta' ? 'Скопировано' : 'Копировать' }}
                      </button>
                      <button type="button" @click="startEditing('cta')">
                        <Pencil :size="14" /> Редактировать
                      </button>
                    </div>
                  </div>
                  <div class="bilingual-grid">
                    <div class="bilingual-col">
                      <span class="bilingual-label">Оригинал</span>
                      <div class="bilingual-pane original-pane compact">
                        <p v-if="selectedReel.original_cta">{{ selectedReel.original_cta }}</p>
                        <p v-else-if="selectedReel.speech_pending" class="bilingual-empty">Расшифровываем речь…</p>
                        <p v-else class="bilingual-empty">В оригинале нет явного CTA</p>
                      </div>
                    </div>
                    <div class="bilingual-col">
                      <span class="bilingual-label">Перевод</span>
                      <div
                        class="bilingual-pane translation-pane compact"
                        :class="{ 'is-loading': remixLoading && editingSection !== 'cta' }"
                      >
                        <textarea
                          v-if="editingSection === 'cta'"
                          v-model="draft"
                          rows="4"
                          :maxlength="sectionLimits.cta"
                          autofocus
                          @keydown.ctrl.enter.prevent="saveSection('cta')"
                        ></textarea>
                        <div v-else-if="remixLoading" class="remix-skel" aria-hidden="true">
                          <span></span><span></span>
                        </div>
                        <p v-else-if="selectedReel.cta">{{ selectedReel.cta }}</p>
                        <p v-else class="bilingual-empty">Перевод появится после Remix</p>
                      </div>
                    </div>
                  </div>
                  <div v-if="editingSection === 'cta'" class="editor-actions bilingual-editor-actions">
                    <span>Ctrl + Enter, чтобы сохранить</span>
                    <button class="cancel-button" type="button" @click="cancelEditing">
                      <X :size="14" /> Отмена
                    </button>
                    <button
                      class="save-button"
                      type="button"
                      :disabled="saveState === 'saving' || !draft.trim()"
                      @click="saveSection('cta')"
                    >
                      <Save :size="14" />
                      {{ saveState === 'saving' ? 'Сохраняем...' : 'Сохранить' }}
                    </button>
                  </div>
                  <span class="counter">
                    {{ editingSection === 'cta' ? draft.length : (selectedReel.cta || '').length }}/{{ sectionLimits.cta }}
                  </span>
                </article>
              </template>

              <template v-else>
              <Transition name="analysis-fade" mode="out-in">
                <div
                  v-if="isAnalysisLoading"
                  key="analysis-loading"
                  class="analysis-loading-stack"
                  aria-busy="true"
                  aria-live="polite"
                >
                  <section class="ai-chat-card analysis-loading-card">
                    <div class="ai-chat-head">
                      <span class="ai-avatar"><Sparkles :size="16" /></span>
                      <div>
                        <strong>Reels AI</strong>
                        <small>Про что ролик</small>
                      </div>
                      <span class="ai-status ai-status-live">
                        <LoaderCircle :size="13" class="spin" />
                        Собираю разбор…
                      </span>
                    </div>
                    <div class="analysis-skeleton">
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-mid"></span>
                      <span class="skel-line skel-short"></span>
                    </div>
                  </section>

                  <article class="insight-card hook-card analysis-loading-card">
                    <div class="insight-title">
                      <span class="insight-icon"><Zap :size="18" fill="currentColor" /></span>
                      <span>
                        <strong>Hook</strong>
                        <small>Первые секунды — стоп-скролл.</small>
                      </span>
                    </div>
                    <div class="analysis-skeleton compact">
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-mid"></span>
                    </div>
                  </article>

                  <article class="insight-card script-card analysis-loading-card">
                    <div class="insight-title">
                      <span class="insight-icon"><FileText :size="18" /></span>
                      <span>
                        <strong>Script</strong>
                        <small>Структура и ключевые тезисы.</small>
                      </span>
                    </div>
                    <div class="analysis-skeleton">
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-mid"></span>
                      <span class="skel-line skel-short"></span>
                    </div>
                  </article>

                  <article class="insight-card cta-card analysis-loading-card">
                    <div class="insight-title">
                      <span class="insight-icon"><Target :size="18" /></span>
                      <span>
                        <strong>Call to Action</strong>
                        <small>Призыв в финале ролика.</small>
                      </span>
                    </div>
                    <div class="analysis-skeleton compact">
                      <span class="skel-line skel-mid"></span>
                      <span class="skel-line skel-short"></span>
                    </div>
                  </article>
                </div>

                <div :key="'analysis-ready-' + analysisRevealKey" class="analysis-ready-stack">
                  <section class="ai-chat-card">
                    <div class="ai-chat-head">
                      <span class="ai-avatar"><Sparkles :size="16" /></span>
                      <div>
                        <strong>Reels AI</strong>
                        <small>Про что ролик</small>
                      </div>
                      <span v-if="isOverviewLoading" class="ai-status ai-status-live">
                        <LoaderCircle :size="13" class="spin" />
                        Собираю разбор…
                      </span>
                    </div>
                    <div v-if="isOverviewLoading" class="analysis-skeleton">
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-wide"></span>
                      <span class="skel-line skel-mid"></span>
                    </div>
                    <div v-else class="ai-chat-body">
                      <p v-for="(paragraph, index) in overviewParagraphs" :key="index">{{ paragraph }}</p>
                    </div>
                  </section>

                  <article class="insight-card hook-card">
                    <div class="insight-title">
                      <span class="insight-icon"><Zap :size="18" fill="currentColor" /></span>
                      <span>
                        <strong>Hook</strong>
                        <small>Оригинал · первые секунды</small>
                      </span>
                      <div class="insight-actions">
                        <button type="button" @click="copySection('hook')">
                          <Copy :size="14" />
                          {{ copiedSection === 'hook' ? 'Скопировано' : 'Копировать' }}
                        </button>
                      </div>
                    </div>
                    <blockquote>«{{ viewOriginalHook || 'Ждём расшифровку оригинала' }}»</blockquote>
                    <span class="counter">
                      {{ viewOriginalHook.length }}/{{ sectionLimits.hook }}
                    </span>
                  </article>

                  <article class="insight-card script-card">
                    <div class="insight-title">
                      <span class="insight-icon"><FileText :size="18" /></span>
                      <span>
                        <strong>Script</strong>
                        <small>Оригинал · основной текст</small>
                      </span>
                      <div class="insight-actions">
                        <button type="button" @click="copySection('script')">
                          <Copy :size="14" />
                          {{ copiedSection === 'script' ? 'Скопировано' : 'Копировать' }}
                        </button>
                      </div>
                    </div>
                    <p v-if="viewOriginalScript" class="script-prose">{{ viewOriginalScript }}</p>
                    <p v-else class="preserve-lines">Ждём расшифровку оригинала</p>
                    <span class="counter">
                      {{ viewOriginalScript.length }}/{{ sectionLimits.script }}
                    </span>
                  </article>

                  <article class="insight-card cta-card">
                    <div class="insight-title">
                      <span class="insight-icon"><Target :size="18" /></span>
                      <span>
                        <strong>Call to Action</strong>
                        <small>Оригинал · финал ролика</small>
                      </span>
                      <div class="insight-actions">
                        <button type="button" @click="copySection('cta')">
                          <Copy :size="14" />
                          {{ copiedSection === 'cta' ? 'Скопировано' : 'Копировать' }}
                        </button>
                      </div>
                    </div>
                    <p class="preserve-lines">
                      {{ viewOriginalCta || 'В оригинале нет явного CTA' }}
                    </p>
                    <span class="counter">
                      {{ viewOriginalCta.length }}/{{ sectionLimits.cta }}
                    </span>
                  </article>

                  <div v-if="selectedReel.why_it_works" class="pro-tip">
                    <Lightbulb :size="19" />
                    <span><strong>Почему это работает</strong> {{ selectedReel.why_it_works }}</span>
                  </div>
                </div>
              </Transition>
              </template>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
