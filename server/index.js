import { mkdirSync } from 'node:fs'
import { createServer } from 'node:http'
import { DatabaseSync } from 'node:sqlite'
import { dirname } from 'node:path'

const port = Number(process.env.PORT ?? 3000)
const databasePath =
  process.env.DATABASE_PATH ??
  (process.env.NODE_ENV === 'production' ? '/data/reels.db' : '.data/reels.db')
const editorIp = process.env.EDITOR_IP?.trim()
const allowedSections = new Set(['hook', 'script', 'cta'])
const limits = {
  hook: 200,
  script: 2000,
  cta: 500,
}

mkdirSync(dirname(databasePath), { recursive: true })

const database = new DatabaseSync(databasePath)
database.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  CREATE TABLE IF NOT EXISTS reel_analysis (
    reel_id TEXT PRIMARY KEY,
    hook TEXT NOT NULL,
    script TEXT NOT NULL,
    cta TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
`)

database
  .prepare(
    `
      INSERT OR IGNORE INTO reel_analysis (reel_id, hook, script, cta)
      VALUES (?, ?, ?, ?)
    `,
  )
  .run(
    '1',
    'Я собрал полноценный SaaS за 1 вечер. Без кода. С помощью Cursor.',
    [
      'Показываю идею',
      'Открываю Cursor и объясняю, что нужно',
      'AI генерирует приложение',
      'Тестирую, вношу правки',
      'Показываю готовый результат',
    ].join('\n'),
    [
      'Попробуйте Cursor сами — ссылка в описании.',
      'И напишите в комментариях, какой проект вы бы собрали!',
    ].join('\n'),
  )

const selectAnalysis = database.prepare(`
  SELECT
    reel_id AS reelId,
    hook,
    script,
    cta,
    updated_at AS updatedAt
  FROM reel_analysis
  WHERE reel_id = ?
`)

const eventClients = new Set()

function sendJson(response, status, body) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  })
  response.end(JSON.stringify(body))
}

function getClientIp(request) {
  const forwarded = request.headers['x-forwarded-for']
  if (typeof forwarded === 'string' && forwarded.length > 0) {
    return forwarded.split(',')[0].trim()
  }

  return request.socket.remoteAddress?.replace(/^::ffff:/, '') ?? ''
}

function canEdit(request) {
  if (!editorIp) return true
  return getClientIp(request) === editorIp
}

async function readJson(request) {
  let body = ''

  for await (const chunk of request) {
    body += chunk
    if (body.length > 50_000) {
      throw new Error('PAYLOAD_TOO_LARGE')
    }
  }

  try {
    return JSON.parse(body || '{}')
  } catch {
    throw new Error('INVALID_JSON')
  }
}

function broadcastAnalysis(analysis) {
  const event = `event: analysis\ndata: ${JSON.stringify(analysis)}\n\n`
  for (const response of eventClients) response.write(event)
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? '/', `http://${request.headers.host ?? 'localhost'}`)

  if (request.method === 'GET' && url.pathname === '/api/health') {
    sendJson(response, 200, { status: 'ok' })
    return
  }

  if (request.method === 'GET' && url.pathname === '/api/events') {
    response.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    })
    response.write(': connected\n\n')
    eventClients.add(response)

    const heartbeat = setInterval(() => response.write(': heartbeat\n\n'), 20_000)
    request.on('close', () => {
      clearInterval(heartbeat)
      eventClients.delete(response)
    })
    return
  }

  const analysisMatch = url.pathname.match(/^\/api\/analysis\/([^/]+)$/)
  if (!analysisMatch) {
    sendJson(response, 404, { error: 'Not found' })
    return
  }

  const reelId = decodeURIComponent(analysisMatch[1])

  if (request.method === 'GET') {
    const analysis = selectAnalysis.get(reelId)
    if (!analysis) {
      sendJson(response, 404, { error: 'Analysis not found' })
      return
    }

    sendJson(response, 200, analysis)
    return
  }

  if (request.method !== 'PUT') {
    sendJson(response, 405, { error: 'Method not allowed' })
    return
  }

  if (!canEdit(request)) {
    sendJson(response, 403, { error: 'Editing is not allowed from this IP address' })
    return
  }

  try {
    const body = await readJson(request)
    const section = typeof body.section === 'string' ? body.section : ''
    const value = typeof body.value === 'string' ? body.value.trim() : ''

    if (!allowedSections.has(section)) {
      sendJson(response, 400, { error: 'Unknown analysis section' })
      return
    }

    if (!value) {
      sendJson(response, 400, { error: 'Text cannot be empty' })
      return
    }

    if (value.length > limits[section]) {
      sendJson(response, 400, {
        error: `Text exceeds the ${limits[section]} character limit`,
      })
      return
    }

    database
      .prepare(
        `
          UPDATE reel_analysis
          SET ${section} = ?, updated_at = CURRENT_TIMESTAMP
          WHERE reel_id = ?
        `,
      )
      .run(value, reelId)

    const analysis = selectAnalysis.get(reelId)
    if (!analysis) {
      sendJson(response, 404, { error: 'Analysis not found' })
      return
    }

    broadcastAnalysis(analysis)
    sendJson(response, 200, analysis)
  } catch (error) {
    if (error.message === 'PAYLOAD_TOO_LARGE') {
      sendJson(response, 413, { error: 'Payload too large' })
      return
    }

    if (error.message === 'INVALID_JSON') {
      sendJson(response, 400, { error: 'Invalid JSON' })
      return
    }

    console.error(error)
    sendJson(response, 500, { error: 'Internal server error' })
  }
})

server.listen(port, '0.0.0.0', () => {
  console.log(`Reels Finder API listening on port ${port}`)
})

function shutdown() {
  for (const response of eventClients) response.end()
  server.close(() => {
    database.close()
    process.exit(0)
  })
}

process.on('SIGINT', shutdown)
process.on('SIGTERM', shutdown)
