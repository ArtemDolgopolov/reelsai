<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  ArrowUpRight,
  Camera,
  Check,
  CircleHelp,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Heart,
  Home,
  Lightbulb,
  LoaderCircle,
  MessageCircle,
  MoreVertical,
  Pencil,
  Play,
  Save,
  Search,
  Sparkles,
  Target,
  Users,
  WandSparkles,
  X,
  Zap,
} from '@lucide/vue'

const pages = ['home', 'competitors', 'detail']

function parseLocationHash() {
  const raw = window.location.hash.replace(/^#/, '').trim()
  if (!raw) return { page: 'home', reelId: null, competitorId: null }
  const [pagePart, ...rest] = raw.split('/')
  const page = pages.includes(pagePart) ? pagePart : 'home'
  const reelId = page === 'detail' && rest[0] ? rest[0] : null
  const competitorId = page === 'competitors' && rest[0] ? rest[0] : null
  return { page, reelId, competitorId }
}

const initialRoute = parseLocationHash()
const currentPage = ref(initialRoute.page)
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
const selectedReel = ref(null)
const detailLoading = ref(Boolean(initialRoute.page === 'detail' && initialRoute.reelId))
const editingSection = ref(null)
const draft = ref('')
const saveState = ref('idle')
const saveError = ref('')
const copiedSection = ref('')
const speechPolling = ref(false)
const analysisRevealKey = ref(0)

let speechPollTimer = null
let copiedTimer = null

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
  return Boolean((reel.hook || '').trim() || (reel.script || '').trim() || (reel.cta || '').trim())
})

const isAnalysisLoading = computed(() => {
  const reel = selectedReel.value
  if (!reel) return false
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

function navigate(page, id = null) {
  currentPage.value = page
  let nextHash = page
  if (page === 'detail' && id) nextHash = `detail/${id}`
  if (page === 'competitors' && id) nextHash = `competitors/${id}`
  if (window.location.hash.replace(/^#/, '') !== nextHash) {
    window.location.hash = nextHash
  }
  if (page === 'home') {
    stopSpeechPolling()
    selectedReel.value = null
    editingSection.value = null
    selectedCompetitorId.value = null
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
  const value = selectedReel.value?.[section] || ''
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
  homeLoading.value = true
  try {
    const response = await fetch('/api/reels?limit=20', { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось загрузить рилсы')
    homeReels.value = await response.json()
  } catch (error) {
    saveError.value = error.message
  } finally {
    homeLoading.value = false
  }
}

async function openReel(reelId, { syncHash = true } = {}) {
  if (!reelId) return
  detailLoading.value = true
  saveError.value = ''
  editingSection.value = null
  copiedSection.value = ''
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
  } catch (error) {
    saveError.value = error.message
    selectedReel.value = null
  } finally {
    detailLoading.value = false
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
  currentPage.value = page
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

onMounted(async () => {
  window.addEventListener('hashchange', syncPageFromHash)
  if (initialRoute.page === 'detail' && initialRoute.reelId) {
    // Open the reel immediately — home discovery can take tens of seconds.
    await openReel(initialRoute.reelId, { syncHash: false })
    void Promise.all([loadHomeReels(), loadInitialCompetitor()])
    return
  }
  await Promise.all([loadHomeReels(), loadInitialCompetitor()])
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncPageFromHash)
  stopSpeechPolling()
  if (copiedTimer) window.clearTimeout(copiedTimer)
})
</script>

<template>
  <div class="app-shell">
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
          :class="{ active: currentPage === 'competitors' }"
          type="button"
          @click="navigate('competitors')"
        >
          <Users :size="18" />
          <span>Конкуренты</span>
        </button>
      </nav>
    </aside>

    <main class="workspace">
      <section v-if="currentPage === 'home'" class="page home-page">
        <header class="page-header home-header">
          <div>
            <span class="eyebrow">Вдохновение на каждый день</span>
            <h1>Главное</h1>
            <p>20 случайных рилсов прямо из Instagram — не только из ваших конкурентов.</p>
          </div>
          <label class="search-field">
            <Search :size="17" />
            <input
              v-model="searchQuery"
              type="search"
              placeholder="Поиск по автору, теме..."
            />
            <kbd>⌘ K</kbd>
          </label>
        </header>

        <div class="section-heading">
          <div>
            <span class="live-dot"></span>
            <strong>Самые просматриваемые</strong>
          </div>
          <span>{{ homeLoading ? 'Загрузка...' : `Найдено ${filteredReels.length}` }}</span>
        </div>

        <div v-if="filteredReels.length" class="reels-grid">
          <article v-for="reel in filteredReels" :key="reel.id" class="reel-card">
            <button class="poster" type="button" @click="openReel(reel.id)">
              <img
                v-if="reel.thumbnail_url"
                :src="thumbSrc(reel.thumbnail_url)"
                :alt="reel.title"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="onThumbError"
              />
              <span class="poster-shade"></span>
              <span class="poster-hook">{{ posterLine(reel) }}</span>
              <span class="duration"><Play :size="10" fill="currentColor" /> {{ reel.duration }}</span>
            </button>
            <div class="reel-meta">
              <span class="mini-avatar">{{ reel.author.slice(1, 2).toUpperCase() }}</span>
              <span>{{ reel.author }}</span>
              <a
                v-if="reel.instagram_url"
                class="open-original-link"
                :href="reel.instagram_url"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Открыть оригинальный Reels"
                @click.stop
              >
                <ExternalLink :size="14" />
              </a>
              <button type="button" aria-label="Дополнительные действия">
                <MoreVertical :size="16" />
              </button>
            </div>
            <h2>{{ reel.title }}</h2>
            <div class="stats-pills">
              <span class="stat-pill views"><Eye :size="14" /> {{ formatViews(reel.views_count) }}</span>
              <span class="stat-pill likes"><Heart :size="14" /> {{ formatViews(reel.likes_count) }}</span>
              <span class="stat-pill comments"><MessageCircle :size="14" /> {{ formatViews(reel.comments_count) }}</span>
            </div>
            <button class="remix-button" type="button" @click="openReel(reel.id)">
              <WandSparkles :size="15" />
              Remix
            </button>
          </article>
        </div>

        <div v-else class="empty-state">
          <Search :size="30" />
          <strong>{{ homeLoading ? 'Загружаем рилсы...' : 'Ничего не найдено' }}</strong>
          <span>Попробуйте изменить запрос или загрузить конкурента</span>
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
                <span><strong>{{ competitor.posts_count }}</strong><small>публикации</small></span>
                <span><strong>{{ formatFollowers(competitor.followers_count) }}</strong><small>подписчики</small></span>
                <span><strong>{{ competitor.following_count }}</strong><small>подписки</small></span>
              </div>
            </article>

            <div class="results-heading">
              <div>
                <h2>{{ competitorReels.length }} рилсов</h2>
                <p>До 20 штук, отсортировано по просмотрам</p>
              </div>
              <span class="success-badge"><Check :size="14" /> {{ competitorMessage || 'Готово' }}</span>
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
                <a
                  v-if="reel.instagram_url"
                  class="open-original-chip"
                  :href="reel.instagram_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink :size="12" />
                  Оригинал
                </a>
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
            <div class="featured-video">
              <img
                v-if="selectedReel.thumbnail_url"
                :src="thumbSrc(selectedReel.thumbnail_url)"
                :alt="selectedReel.title"
                referrerpolicy="no-referrer"
                @error="onThumbError"
              />
              <span class="poster-shade"></span>
              <span class="poster-hook">{{ posterLine(selectedReel) }}</span>
              <button type="button" aria-label="Воспроизвести видео">
                <Play :size="24" fill="currentColor" />
              </button>
              <span class="video-progress"><i></i></span>
              <span class="video-time">0:00 / {{ selectedDurationLabel }}</span>
            </div>
            <div class="video-actions">
              <button class="primary-button wide" type="button">
                <WandSparkles :size="17" />
                Создать Remix
              </button>
              <button class="icon-button" type="button" aria-label="Другие действия">
                <MoreVertical :size="18" />
              </button>
            </div>
          </div>

          <div class="analysis-column">
            <header class="detail-title">
              <div>
                <span class="eyebrow">AI-разбор</span>
                <h1>{{ selectedReel.title }}</h1>
              </div>
              <button class="icon-button" type="button" aria-label="Другие действия">
                <MoreVertical :size="18" />
              </button>
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
              <span class="stat-pill duration"><Play :size="15" /> <strong>{{ selectedDurationLabel }}</strong></span>
            </div>

            <div class="insight-list">
              <div v-if="saveState === 'saved'" class="save-notice success">
                <Check :size="15" />
                Изменения сохранены
              </div>
              <div v-if="saveError" class="save-notice error">
                <CircleHelp :size="15" />
                {{ saveError }}
              </div>

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
                        <small>Первые секунды — стоп-скролл.</small>
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
                    <div v-if="editingSection === 'hook'" class="section-editor">
                      <textarea
                        v-model="draft"
                        rows="3"
                        :maxlength="sectionLimits.hook"
                        autofocus
                        @keydown.ctrl.enter.prevent="saveSection('hook')"
                      ></textarea>
                      <div class="editor-actions">
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
                    </div>
                    <blockquote v-else>«{{ selectedReel.hook || 'Добавь hook вручную' }}»</blockquote>
                    <span class="counter">
                      {{ editingSection === 'hook' ? draft.length : (selectedReel.hook || '').length }}/{{ sectionLimits.hook }}
                    </span>
                  </article>

                  <article class="insight-card script-card">
                    <div class="insight-title">
                      <span class="insight-icon"><FileText :size="18" /></span>
                      <span>
                        <strong>Script</strong>
                        <small>Структура и ключевые тезисы.</small>
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
                    <div v-if="editingSection === 'script'" class="section-editor">
                      <textarea
                        v-model="draft"
                        rows="7"
                        :maxlength="sectionLimits.script"
                        autofocus
                        @keydown.ctrl.enter.prevent="saveSection('script')"
                      ></textarea>
                      <div class="editor-actions">
                        <span>Каждый пункт с новой строки</span>
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
                    </div>
                    <p v-if="scriptBody" class="script-prose">{{ scriptBody }}</p>
                    <p v-else class="preserve-lines">Добавь скрипт вручную</p>
                    <span class="counter">
                      {{ editingSection === 'script' ? draft.length : scriptBody.length }}/{{ sectionLimits.script }}
                    </span>
                  </article>

                  <article class="insight-card cta-card">
                    <div class="insight-title">
                      <span class="insight-icon"><Target :size="18" /></span>
                      <span>
                        <strong>Call to Action</strong>
                        <small>Призыв в финале ролика.</small>
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
                    <div v-if="editingSection === 'cta'" class="section-editor">
                      <textarea
                        v-model="draft"
                        rows="4"
                        :maxlength="sectionLimits.cta"
                        autofocus
                        @keydown.ctrl.enter.prevent="saveSection('cta')"
                      ></textarea>
                      <div class="editor-actions">
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
                    </div>
                    <p v-else class="preserve-lines">
                      {{ selectedReel.cta || 'Сохрани и попробуй этот формат в своём следующем рилсе.' }}
                    </p>
                    <span class="counter">
                      {{ editingSection === 'cta' ? draft.length : (selectedReel.cta || '').length }}/{{ sectionLimits.cta }}
                    </span>
                  </article>

                  <div v-if="selectedReel.why_it_works" class="pro-tip">
                    <Lightbulb :size="19" />
                    <span><strong>Почему это работает</strong> {{ selectedReel.why_it_works }}</span>
                  </div>
                </div>
              </Transition>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
