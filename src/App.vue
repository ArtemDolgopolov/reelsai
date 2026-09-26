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
  FileText,
  Home,
  Lightbulb,
  MoreVertical,
  Pencil,
  Play,
  Search,
  Settings,
  Sparkles,
  Target,
  Users,
  WandSparkles,
  Zap,
} from '@lucide/vue'

const pages = ['home', 'competitors', 'detail']
const pageFromHash = window.location.hash.slice(1)
const currentPage = ref(pages.includes(pageFromHash) ? pageFromHash : 'home')
const searchQuery = ref('')
const competitorHandle = ref('@vibecoding_creator')
const competitorLoaded = ref(true)
const detailTab = ref('analysis')

const reels = [
  {
    id: 1,
    title: 'Как я собрал SaaS за 1 вечер с Cursor',
    author: '@vibecoding_creator',
    duration: '0:28',
    image:
      'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=700&q=85',
    hook: 'BUILD APPS WITH AI',
  },
  {
    id: 2,
    title: 'От идеи до приложения за 10 минут',
    author: '@buildwithmarco',
    duration: '0:35',
    image:
      'https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=700&q=85',
    hook: 'IDEA TO APP IN 10 MIN',
  },
  {
    id: 3,
    title: 'Мои 5 любимых AI-инструментов',
    author: '@futuredev',
    duration: '0:41',
    image:
      'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=700&q=85',
    hook: 'VIBE CODING TIPS',
  },
  {
    id: 4,
    title: 'Больше не пишу код вручную',
    author: '@devwithalex',
    duration: '0:29',
    image:
      'https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=700&q=85',
    hook: 'JUST DESCRIBE IT',
  },
  {
    id: 5,
    title: 'Как я запустил продукт с помощью AI',
    author: '@nocodeandy',
    duration: '0:52',
    image:
      'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=700&q=85',
    hook: 'FROM PROMPT TO PRODUCT',
  },
  {
    id: 6,
    title: 'AI-инструменты, которые реально использую',
    author: '@buildinpublic',
    duration: '0:35',
    image:
      'https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=700&q=85',
    hook: 'AI TOOLS I ACTUALLY USE',
  },
  {
    id: 7,
    title: 'AI-инструменты в 2024',
    author: '@vibecoding_creator',
    duration: '0:43',
    image:
      'https://images.unsplash.com/photo-1550439062-609e1531270e?auto=format&fit=crop&w=700&q=85',
    hook: 'AI TOOLS IN 2024',
  },
  {
    id: 8,
    title: 'Мой сетап для вайб-кодинга',
    author: '@vibecoding_creator',
    duration: '0:27',
    image:
      'https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=700&q=85',
    hook: 'MY CODING SETUP',
  },
  {
    id: 9,
    title: '3 ошибки новичков',
    author: '@vibecoding_creator',
    duration: '0:46',
    image:
      'https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=700&q=85',
    hook: '3 BEGINNER MISTAKES',
  },
  {
    id: 10,
    title: 'Лучшие промпты для Cursor',
    author: '@vibecoding_creator',
    duration: '0:49',
    image:
      'https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=700&q=85',
    hook: 'BEST CURSOR PROMPTS',
  },
]

const filteredReels = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return reels.slice(0, 6)
  return reels.filter(
    (reel) =>
      reel.title.toLowerCase().includes(query) ||
      reel.author.toLowerCase().includes(query),
  )
})

function navigate(page) {
  currentPage.value = page
  window.location.hash = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function openReel() {
  detailTab.value = 'analysis'
  navigate('detail')
}

function loadCompetitor() {
  competitorLoaded.value = true
}

function syncPageFromHash() {
  const page = window.location.hash.slice(1)
  if (pages.includes(page)) currentPage.value = page
}

onMounted(() => window.addEventListener('hashchange', syncPageFromHash))
onBeforeUnmount(() => window.removeEventListener('hashchange', syncPageFromHash))
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
          <span>Обновлено 12 минут назад</span>
        </div>

        <div v-if="filteredReels.length" class="reels-grid">
          <article v-for="reel in filteredReels" :key="reel.id" class="reel-card">
            <button class="poster" type="button" @click="openReel">
              <img :src="reel.image" :alt="reel.title" />
              <span class="poster-shade"></span>
              <span class="poster-hook">{{ reel.hook }}</span>
              <span class="duration"><Play :size="10" fill="currentColor" /> {{ reel.duration }}</span>
            </button>
            <div class="reel-meta">
              <span class="mini-avatar">{{ reel.author.slice(1, 2).toUpperCase() }}</span>
              <span>{{ reel.author }}</span>
              <button type="button" aria-label="Дополнительные действия">
                <MoreVertical :size="16" />
              </button>
            </div>
            <h2>{{ reel.title }}</h2>
            <button class="remix-button" type="button" @click="openReel">
              <WandSparkles :size="15" />
              Remix
            </button>
          </article>
        </div>

        <div v-else class="empty-state">
          <Search :size="30" />
          <strong>Ничего не найдено</strong>
          <span>Попробуйте изменить запрос</span>
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
          <button class="primary-button" type="button" @click="loadCompetitor">
            Загрузить
            <ArrowUpRight :size="17" />
          </button>
        </div>

        <template v-if="competitorLoaded">
          <article class="profile-card">
            <div class="profile-main">
              <img :src="reels[0].image" alt="Alex Carter" />
              <div>
                <strong>Alex Carter</strong>
                <span>@vibecoding_creator</span>
                <p>Building AI apps. No code, just ideas.<br />Documenting the journey.</p>
              </div>
            </div>
            <div class="profile-stats">
              <span><strong>342</strong><small>публикации</small></span>
              <span><strong>1.2M</strong><small>подписчики</small></span>
              <span><strong>102</strong><small>подписки</small></span>
            </div>
          </article>

          <div class="results-heading">
            <div>
              <h2>Найдено 20 последних рилсов</h2>
              <p>Отсортировано по вовлечённости</p>
            </div>
            <span class="success-badge"><Check :size="14" /> Успешно загружено через API</span>
          </div>

          <div class="compact-reels-grid">
            <button
              v-for="reel in reels"
              :key="reel.id"
              class="compact-reel"
              type="button"
              @click="openReel"
            >
              <span class="compact-poster">
                <img :src="reel.image" :alt="reel.title" />
                <span class="duration"><Play :size="9" fill="currentColor" /> {{ reel.duration }}</span>
              </span>
              <strong>{{ reel.title }}</strong>
            </button>
          </div>
        </template>
      </section>

      <section v-else class="page detail-page">
        <button class="back-button" type="button" @click="navigate('home')">
          <ArrowLeft :size="17" />
          Назад к списку
        </button>

        <div class="detail-layout">
          <div class="video-column">
            <div class="featured-video">
              <img :src="reels[0].image" alt="Как я собрал SaaS за 1 вечер с Cursor" />
              <span class="poster-shade"></span>
              <span class="poster-hook">BUILD<br />APPS<br />WITH AI</span>
              <button type="button" aria-label="Воспроизвести видео">
                <Play :size="24" fill="currentColor" />
              </button>
              <span class="video-progress"><i></i></span>
              <span class="video-time">0:00 / 0:28</span>
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
                <h1>Как я собрал SaaS за 1 вечер с Cursor</h1>
              </div>
              <button class="icon-button" type="button" aria-label="Другие действия">
                <MoreVertical :size="18" />
              </button>
            </header>

            <div class="creator-row">
              <span class="creator-avatar">A</span>
              <span>
                <strong>Alex Carter</strong>
                <small>@vibecoding_creator</small>
              </span>
              <span class="creator-meta">0:28 · 1.2M просмотров · 2 недели назад</span>
              <button class="instagram-button" type="button">
                <Camera :size="15" />
                Открыть в Instagram
                <ArrowUpRight :size="14" />
              </button>
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
              <article class="insight-card hook-card">
                <div class="insight-title">
                  <span class="insight-icon"><Zap :size="18" fill="currentColor" /></span>
                  <span>
                    <strong>Hook</strong>
                    <small>Первые 3 секунды — то, что останавливает скролл.</small>
                  </span>
                  <button type="button"><Pencil :size="14" /> Редактировать</button>
                </div>
                <blockquote>«Я собрал полноценный SaaS за 1 вечер. Без кода. С помощью Cursor.»</blockquote>
                <span class="counter">20/200</span>
              </article>

              <article class="insight-card script-card">
                <div class="insight-title">
                  <span class="insight-icon"><FileText :size="18" /></span>
                  <span>
                    <strong>Script</strong>
                    <small>Основной сценарий ролика и ключевые тезисы.</small>
                  </span>
                  <button type="button"><Pencil :size="14" /> Редактировать</button>
                </div>
                <ol>
                  <li>Показываю идею</li>
                  <li>Открываю Cursor и объясняю, что нужно</li>
                  <li>AI генерирует приложение</li>
                  <li>Тестирую, вношу правки</li>
                  <li>Показываю готовый результат</li>
                </ol>
                <span class="counter">350/2000</span>
              </article>

              <article class="insight-card cta-card">
                <div class="insight-title">
                  <span class="insight-icon"><Target :size="18" /></span>
                  <span>
                    <strong>Call to Action</strong>
                    <small>Призыв к действию в конце ролика.</small>
                  </span>
                  <button type="button"><Pencil :size="14" /> Редактировать</button>
                </div>
                <p>Попробуйте Cursor сами — ссылка в описании.<br />И напишите в комментариях, какой проект вы бы собрали!</p>
                <span class="counter">95/500</span>
              </article>

              <div class="pro-tip">
                <Lightbulb :size="19" />
                <span><strong>Почему это работает</strong> Конкретный результат, короткий срок и понятная трансформация создают сильное любопытство.</span>
              </div>
            </div>

            <div v-else class="transcript-panel">
              <span class="transcript-badge"><Bolt :size="14" /> Автоматическая расшифровка</span>
              <p>
                Сегодня покажу, как я собрал полноценное SaaS-приложение всего за один
                вечер. Я не писал код вручную — вместо этого описал идею в Cursor,
                получил рабочий прототип и доработал его с помощью AI.
              </p>
              <p>
                В конце покажу результат и дам точный промпт, с которого можно начать
                собственный проект.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
