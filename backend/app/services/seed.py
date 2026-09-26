from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import Competitor, CompetitorStatus, Reel, ReelStatus

SEED_HANDLE = "vibecoding_creator"

SEED_REELS = [
    {
        "external_id": "seed-1",
        "title": "Как я собрал SaaS за 1 вечер с Cursor",
        "overlay_text": "BUILD APPS WITH AI",
        "duration_seconds": 28,
        "views_count": 1_200_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=700&q=85",
        "hook": "Я собрал полноценный SaaS за 1 вечер. Без кода. С помощью Cursor.",
        "script": "\n".join(
            [
                "Показываю идею",
                "Открываю Cursor и объясняю, что нужно",
                "AI генерирует приложение",
                "Тестирую, вношу правки",
                "Показываю готовый результат",
            ]
        ),
        "cta": "Попробуйте Cursor сами — ссылка в описании.\nИ напишите в комментариях, какой проект вы бы собрали!",
        "transcript": (
            "Сегодня покажу, как я собрал полноценное SaaS-приложение всего за один вечер. "
            "Я не писал код вручную — вместо этого описал идею в Cursor, получил рабочий прототип "
            "и доработал его с помощью AI.\n\nВ конце покажу результат и дам точный промпт, "
            "с которого можно начать собственный проект."
        ),
        "why_it_works": "Конкретный результат, короткий срок и понятная трансформация создают сильное любопытство.",
        "days_ago": 14,
    },
    {
        "external_id": "seed-2",
        "title": "От идеи до приложения за 10 минут",
        "overlay_text": "IDEA TO APP IN 10 MIN",
        "duration_seconds": 35,
        "views_count": 860_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=700&q=85",
        "hook": "От идеи до приложения за 10 минут — вот как.",
        "script": "Показываю идею\nСобираю прототип\nПоказываю результат",
        "cta": "Сохрани и попробуй сам.",
        "days_ago": 10,
    },
    {
        "external_id": "seed-3",
        "title": "Мои 5 любимых AI-инструментов",
        "overlay_text": "VIBE CODING TIPS",
        "duration_seconds": 41,
        "views_count": 540_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=700&q=85",
        "hook": "Эти 5 AI-инструментов экономят мне часы каждый день.",
        "script": "Cursor\nChatGPT\nClaude\nPerplexity\nNotion AI",
        "cta": "Напиши в комментариях свой любимый инструмент.",
        "days_ago": 8,
    },
    {
        "external_id": "seed-4",
        "title": "Больше не пишу код вручную",
        "overlay_text": "JUST DESCRIBE IT",
        "duration_seconds": 29,
        "views_count": 720_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=700&q=85",
        "hook": "Я больше не пишу код вручную — только описываю.",
        "script": "Проблема\nПромпт\nРезультат",
        "cta": "Попробуй подход и расскажи, что получилось.",
        "days_ago": 7,
    },
    {
        "external_id": "seed-5",
        "title": "Как я запустил продукт с помощью AI",
        "overlay_text": "FROM PROMPT TO PRODUCT",
        "duration_seconds": 52,
        "views_count": 910_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=700&q=85",
        "hook": "От промпта до продукта — мой полный путь.",
        "script": "Идея\nMVP\nЗапуск\nПервые пользователи",
        "cta": "Ссылка на шаблон в описании.",
        "days_ago": 6,
    },
    {
        "external_id": "seed-6",
        "title": "AI-инструменты, которые реально использую",
        "overlay_text": "AI TOOLS I ACTUALLY USE",
        "duration_seconds": 35,
        "views_count": 430_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=700&q=85",
        "hook": "Вот AI-инструменты, которые я реально использую каждый день.",
        "script": "Код\nДизайн\nКонтент\nАналитика",
        "cta": "Сохрани список на потом.",
        "days_ago": 5,
    },
    {
        "external_id": "seed-7",
        "title": "AI-инструменты в 2024",
        "overlay_text": "AI TOOLS IN 2024",
        "duration_seconds": 43,
        "views_count": 380_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1550439062-609e1531270e?auto=format&fit=crop&w=700&q=85",
        "hook": "Лучшие AI-инструменты прямо сейчас.",
        "script": "Что изменилось\nЧто стоит попробовать\nЧто уже устарело",
        "cta": "Подпишись, чтобы не пропустить обновления.",
        "days_ago": 4,
    },
    {
        "external_id": "seed-8",
        "title": "Мой сетап для вайб-кодинга",
        "overlay_text": "MY CODING SETUP",
        "duration_seconds": 27,
        "views_count": 295_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?auto=format&fit=crop&w=700&q=85",
        "hook": "Мой сетап для вайб-кодинга выглядит так.",
        "script": "Редактор\nМодели\nПроцесс",
        "cta": "Скажи, чего не хватает в твоём сетапе.",
        "days_ago": 3,
    },
    {
        "external_id": "seed-9",
        "title": "3 ошибки новичков",
        "overlay_text": "3 BEGINNER MISTAKES",
        "duration_seconds": 46,
        "views_count": 610_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&w=700&q=85",
        "hook": "Три ошибки, из-за которых новички буксуют с AI.",
        "script": "Слишком общие промпты\nНет итераций\nНет цели",
        "cta": "Какую ошибку делал ты? Пиши в комментариях.",
        "days_ago": 2,
    },
    {
        "external_id": "seed-10",
        "title": "Лучшие промпты для Cursor",
        "overlay_text": "BEST CURSOR PROMPTS",
        "duration_seconds": 49,
        "views_count": 770_000,
        "thumbnail_url": "https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=700&q=85",
        "hook": "Эти промпты для Cursor дают лучший результат.",
        "script": "Контекст\nОграничения\nФормат ответа\nПроверка",
        "cta": "Сохрани и используй в следующем проекте.",
        "days_ago": 1,
    },
]


def ensure_seed_data(session: Session) -> Competitor:
    competitor = session.exec(
        select(Competitor).where(Competitor.username == SEED_HANDLE)
    ).first()

    if competitor is None:
        competitor = Competitor(
            username=SEED_HANDLE,
            full_name="Alex Carter",
            bio="Building AI apps. No code, just ideas.\nDocumenting the journey.",
            avatar_url=SEED_REELS[0]["thumbnail_url"],
            posts_count=342,
            followers_count=1_200_000,
            following_count=102,
            status=CompetitorStatus.ready,
        )
        session.add(competitor)
        session.commit()
        session.refresh(competitor)

    existing = {
        reel.external_id
        for reel in session.exec(select(Reel).where(Reel.competitor_id == competitor.id)).all()
        if reel.external_id
    }

    now = datetime.now(timezone.utc)
    created = False
    for item in SEED_REELS:
        if item["external_id"] in existing:
            continue
        session.add(
            Reel(
                competitor_id=competitor.id,
                external_id=item["external_id"],
                title=item["title"],
                caption=item["title"],
                thumbnail_url=item["thumbnail_url"],
                duration_seconds=item["duration_seconds"],
                views_count=item["views_count"],
                overlay_text=item["overlay_text"],
                hook=item["hook"],
                script=item["script"],
                cta=item["cta"],
                transcript=item.get("transcript"),
                why_it_works=item.get("why_it_works"),
                posted_at=now - timedelta(days=item["days_ago"]),
                status=ReelStatus.ready,
            )
        )
        created = True

    if created:
        session.commit()

    return competitor
