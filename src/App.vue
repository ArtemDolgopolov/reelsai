<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  ArrowUpRight,
  Bolt,
  Camera,
  Check,
  ChevronRight,
  CircleHelp,
  ExternalLink,
  Eye,
  FileText,
  Heart,
  Home,
  Lightbulb,
  MessageCircle,
  MoreVertical,
  Pencil,
  Play,
  Save,
  Search,
  Settings,
  Sparkles,
  Target,
  Users,
  WandSparkles,
  X,
  Zap,
} from '@lucide/vue'

const pages = ['home', 'competitors', 'detail']
const pageFromHash = window.location.hash.slice(1)
const currentPage = ref(pages.includes(pageFromHash) ? pageFromHash : 'home')
const searchQuery = ref('')
const competitorHandle = ref('@vibecoding_creator')
const competitor = ref(null)
const competitorReels = ref([])
const competitorMessage = ref('')
const competitorLoading = ref(false)
const homeReels = ref([])
const homeLoading = ref(true)
const selectedReel = ref(null)
const detailLoading = ref(false)
const detailTab = ref('analysis')
const editingSection = ref(null)
const draft = ref('')
const saveState = ref('idle')
const saveError = ref('')

const sectionLimits = {
  hook: 200,
  script: 2000,
  cta: 500,
}

const scriptLines = computed(() =>
  (selectedReel.value?.script || '')
    .split(/\r?\n/)
    .filter((line) => line.trim()),
)

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
    return `${String(value).replace(/\.0$/, '')}M`
  }
  if (count >= 1_000) {
    const value = count / 1_000
    return `${String(value).replace(/\.0$/, '')}K`
  }
  return String(count)
}

function formatFollowers(count) {
  return formatViews(count)
}

function navigate(page) {
  currentPage.value = page
  window.location.hash = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
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

async function openReel(reelId) {
  detailTab.value = 'analysis'
  detailLoading.value = true
  saveError.value = ''
  editingSection.value = null
  navigate('detail')

  try {
    const response = await fetch(`/api/reels/${reelId}`, { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось открыть рилс')
    selectedReel.value = await response.json()
  } catch (error) {
    saveError.value = error.message
  } finally {
    detailLoading.value = false
  }
}

async function loadInitialCompetitor() {
  try {
    const response = await fetch('/api/competitors', { cache: 'no-store' })
    if (!response.ok) return
    const competitors = await response.json()
    if (!competitors.length) return

    competitor.value = competitors[0]
    competitorHandle.value = `@${competitors[0].username}`
    const reelsResponse = await fetch(
      `/api/competitors/${competitors[0].id}/reels`,
      { cache: 'no-store' },
    )
    if (reelsResponse.ok) competitorReels.value = await reelsResponse.json()
    competitorMessage.value = 'Загружено из PostgreSQL'
  } catch {
    // The main feed still remains usable if the optional profile request fails.
  }
}

async function loadCompetitor(forceRefresh = false) {
  competitorLoading.value = true
  competitorMessage.value = ''
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

    competitor.value = body.competitor
    competitorReels.value = body.reels
    competitorMessage.value = body.message
    competitorHandle.value = `@${body.competitor.username}`
    await loadHomeReels()
  } catch (error) {
    saveError.value = error.message
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
  const page = window.location.hash.slice(1)
  if (pages.includes(page)) currentPage.value = page
}

onMounted(async () => {
  window.addEventListener('hashchange', syncPageFromHash)
  await Promise.all([loadHomeReels(), loadInitialCompetitor()])
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncPageFromHash)
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

      <div class="sidebar-bottom">
        <button class="nav-item subtle" type="button">
          <CircleHelp :size="18" />
          <span>Помощь</span>
        </button>
        <button class="nav-item subtle" type="button">
          <Settings :size="18" />
          <span>Настройки</span>
        </button>
        <div class="plan-card">
          <span class="plan-icon">👑</span>
          <span>
            <strong>Pro план</strong>
            <small>Безлимитные AI-анализы</small>
          </span>
          <ChevronRight :size="16" />
        </div>
      </div>
    </aside>

    <main class="workspace">
      <section v-if="currentPage === 'home'" class="page home-page">
        <header class="page-header home-header">
          <div>
            <span class="eyebrow">Вдохновение на каждый день</span>
            <h1>Главное</h1>
            <p>Тренды, которые набирают обороты прямо сейчас.</p>
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
            <strong>В тренде сегодня</strong>
          </div>
          <span>{{ homeLoading ? 'Загрузка...' : `Найдено ${filteredReels.length}` }}</span>
        </div>

        <div v-if="filteredReels.length" class="reels-grid">
          <article v-for="reel in filteredReels" :key="reel.id" class="reel-card">
            <button class="poster" type="button" @click="openReel(reel.id)">
              <img :src="reel.thumbnail_url" :alt="reel.title" />
              <span class="poster-shade"></span>
              <span class="poster-hook">{{ reel.overlay_text || reel.title }}</span>
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
            <span class="eyebrow">Исследование ниши</span>
            <h1>Конкуренты</h1>
            <p>Загрузите Instagram-аккаунт и изучите его лучшие форматы.</p>
          </div>
        </header>

        <div class="competitor-loader">
          <label>
            <Camera :size="20" />
            <input v-model="competitorHandle" aria-label="Instagram username" />
          </label>
          <button
            class="primary-button"
            type="button"
            :disabled="competitorLoading"
            @click="loadCompetitor(false)"
          >
            {{ competitorLoading ? 'Расшифровываем...' : 'Загрузить' }}
            <ArrowUpRight :size="17" />
          </button>
        </div>

        <template v-if="competitor">
          <article class="profile-card">
            <div class="profile-main">
              <img :src="competitor.avatar_url" :alt="competitor.full_name || competitor.username" />
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
              <h2>Найдено {{ competitorReels.length }} последних рилсов</h2>
              <p>Отсортировано по вовлечённости</p>
            </div>
            <span class="success-badge"><Check :size="14" /> {{ competitorMessage || 'Готово' }}</span>
          </div>

          <div class="compact-reels-grid">
            <article
              v-for="reel in competitorReels"
              :key="reel.id"
              class="compact-reel"
            >
              <button class="compact-poster" type="button" @click="openReel(reel.id)">
                <img :src="reel.thumbnail_url" :alt="reel.title" />
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
        </template>
      </section>

      <section v-else class="page detail-page">
        <button class="back-button" type="button" @click="navigate('home')">
          <ArrowLeft :size="17" />
          Назад к списку
        </button>

        <div v-if="detailLoading || !selectedReel" class="empty-state">
          <Sparkles :size="30" />
          <strong>{{ detailLoading ? 'Открываем рилс...' : 'Рилс не выбран' }}</strong>
        </div>

        <div v-else class="detail-layout">
          <div class="video-column">
            <div class="featured-video">
              <img :src="selectedReel.thumbnail_url" :alt="selectedReel.title" />
              <span class="poster-shade"></span>
              <span class="poster-hook">{{ selectedReel.overlay_text || selectedReel.title }}</span>
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
                <span class="eyebrow">Разбор трендового ролика</span>
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

            <div class="detail-tabs" role="tablist">
              <button
                :class="{ active: detailTab === 'analysis' }"
                type="button"
                @click="detailTab = 'analysis'"
              >
                <Sparkles :size="16" />
                AI Анализ
              </button>
              <button
                :class="{ active: detailTab === 'description' }"
                type="button"
                @click="detailTab = 'description'"
              >
                Описание и расшифровка
              </button>
            </div>

            <div v-if="detailTab === 'analysis'" class="insight-list">
              <div v-if="saveState === 'saved'" class="save-notice success">
                <Check :size="15" />
                Изменения сохранены в PostgreSQL
              </div>
              <div v-if="saveError" class="save-notice error">
                <CircleHelp :size="15" />
                {{ saveError }}
              </div>

              <article class="insight-card hook-card">
                <div class="insight-title">
                  <span class="insight-icon"><Zap :size="18" fill="currentColor" /></span>
                  <span>
                    <strong>Hook</strong>
                    <small>Первые 3 секунды — то, что останавливает скролл.</small>
                  </span>
                  <button
                    v-if="editingSection !== 'hook'"
                    type="button"
                    @click="startEditing('hook')"
                  >
                    <Pencil :size="14" /> Редактировать
                  </button>
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
                <blockquote v-else>«{{ selectedReel.hook }}»</blockquote>
                <span class="counter">
                  {{ editingSection === 'hook' ? draft.length : selectedReel.hook.length }}/{{ sectionLimits.hook }}
                </span>
              </article>

              <article class="insight-card script-card">
                <div class="insight-title">
                  <span class="insight-icon"><FileText :size="18" /></span>
                  <span>
                    <strong>Script</strong>
                    <small>Основной сценарий ролика и ключевые тезисы.</small>
                  </span>
                  <button
                    v-if="editingSection !== 'script'"
                    type="button"
                    @click="startEditing('script')"
                  >
                    <Pencil :size="14" /> Редактировать
                  </button>
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
                    <span>Каждый пункт пишите с новой строки</span>
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
                <ol v-else>
                  <li v-for="line in scriptLines" :key="line">{{ line }}</li>
                </ol>
                <span class="counter">
                  {{ editingSection === 'script' ? draft.length : selectedReel.script.length }}/{{ sectionLimits.script }}
                </span>
              </article>

              <article class="insight-card cta-card">
                <div class="insight-title">
                  <span class="insight-icon"><Target :size="18" /></span>
                  <span>
                    <strong>Call to Action</strong>
                    <small>Призыв к действию в конце ролика.</small>
                  </span>
                  <button
                    v-if="editingSection !== 'cta'"
                    type="button"
                    @click="startEditing('cta')"
                  >
                    <Pencil :size="14" /> Редактировать
                  </button>
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
                <p v-else class="preserve-lines">{{ selectedReel.cta }}</p>
                <span class="counter">
                  {{ editingSection === 'cta' ? draft.length : selectedReel.cta.length }}/{{ sectionLimits.cta }}
                </span>
              </article>

              <div v-if="selectedReel.why_it_works" class="pro-tip">
                <Lightbulb :size="19" />
                <span><strong>Почему это работает</strong> {{ selectedReel.why_it_works }}</span>
              </div>
            </div>

            <div v-else class="transcript-panel">
              <div class="transcript-block">
                <span class="transcript-badge"><Bolt :size="14" /> Что говорит автор (аудио)</span>
                <p class="preserve-lines">
                  {{
                    selectedReel.transcript && selectedReel.transcript.length >= 40
                      ? selectedReel.transcript
                      : 'Расшифровка речи пока недоступна. Нажмите «Загрузить» у конкурента ещё раз — Whisper достанет текст из аудио рилса.'
                  }}
                </p>
              </div>
              <div v-if="selectedReel.caption" class="transcript-block caption-block">
                <span class="transcript-badge muted">Подпись Instagram</span>
                <p class="preserve-lines">{{ selectedReel.caption }}</p>
              </div>
              <a
                v-if="selectedReel.instagram_url"
                class="instagram-button primary-original inline-original"
                :href="selectedReel.instagram_url"
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink :size="15" />
                Открыть оригинальный Reels
              </a>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
