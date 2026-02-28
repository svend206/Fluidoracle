/**
 * Hydraulic Filter Platform — API Client
 *
 * All backend calls go through here. In dev, Vite proxies /api to localhost:8000.
 * In production, the backend serves the frontend so no proxy is needed.
 */

const BASE = '/api'

// ---------------------------------------------------------------------------
// Auth token management (localStorage)
// ---------------------------------------------------------------------------

export function getAuthToken() {
  return localStorage.getItem('spray_auth_token') || ''
}

export function setAuthToken(token) {
  localStorage.setItem('spray_auth_token', token)
}

export function clearAuthToken() {
  localStorage.removeItem('spray_auth_token')
}

export function isAuthenticated() {
  return !!localStorage.getItem('spray_auth_token')
}

// ---------------------------------------------------------------------------
// Base request helper
// ---------------------------------------------------------------------------

async function request(url, options = {}) {
  const { headers: optHeaders, ...restOptions } = options
  const authToken = getAuthToken()
  const headers = {
    'Content-Type': 'application/json',
    ...optHeaders,
  }
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }

  const res = await fetch(`${BASE}${url}`, {
    ...restOptions,
    headers,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }

  return res.json()
}

// --- Questions ---

export async function askQuestion(question) {
  return request('/ask', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

/**
 * Stream an expert answer via SSE.
 *
 * @param {string} question
 * @param {Object} callbacks
 * @param {function} callbacks.onStatus  — called with {stage, confidence?, sources?, warnings?}
 * @param {function} callbacks.onChunk   — called with {text} for each token
 * @param {function} callbacks.onComplete — called with {answer, confidence, sources, warnings}
 * @param {function} callbacks.onSaved   — called with {question_id} after DB save
 * @param {function} callbacks.onError   — called with Error object
 */
export async function askQuestionStream(question, callbacks = {}) {
  const { onStatus, onChunk, onComplete, onSaved, onError } = callbacks

  try {
    const res = await fetch(`${BASE}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Request failed: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Parse SSE events from buffer
      const lines = buffer.split('\n')
      buffer = ''
      let currentEvent = null

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ') && currentEvent) {
          try {
            const data = JSON.parse(line.slice(6))
            switch (currentEvent) {
              case 'status':
                onStatus?.(data)
                break
              case 'chunk':
                onChunk?.(data)
                break
              case 'complete':
                onComplete?.(data)
                break
              case 'saved':
                onSaved?.(data)
                break
              case 'error':
                onError?.(new Error(data.message || 'Unknown streaming error'))
                break
            }
          } catch {
            // Incomplete JSON — put back in buffer
            buffer = `event: ${currentEvent}\n${line}\n`
          }
          currentEvent = null
        } else if (line === '') {
          currentEvent = null
        } else {
          // Incomplete line — put back in buffer
          buffer += line + '\n'
        }
      }
    }
  } catch (err) {
    onError?.(err)
  }
}

export async function getQuestions(page = 1, limit = 20) {
  return request(`/questions?page=${page}&limit=${limit}`)
}

export async function getQuestion(id) {
  return request(`/questions/${id}`)
}

// --- Votes ---

export async function vote(questionId, direction) {
  return request(`/questions/${questionId}/vote`, {
    method: 'POST',
    body: JSON.stringify({ direction }),
  })
}

// --- Comments ---

export async function getComments(questionId) {
  return request(`/questions/${questionId}/comments`)
}

export async function addComment(questionId, body, isCorrection = false, authorName = 'Anonymous') {
  return request(`/questions/${questionId}/comments`, {
    method: 'POST',
    body: JSON.stringify({
      body,
      is_correction: isCorrection,
      author_name: authorName,
    }),
  })
}

// --- Stats ---

export async function getStats() {
  return request('/stats')
}

// --- Authentication (passwordless) ---

export async function authSendCode(email) {
  return request('/auth/send-code', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export async function authVerifyCode(email, code) {
  return request('/auth/verify-code', {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  })
}

export async function authLogout() {
  return request('/auth/logout', { method: 'POST' })
}

export async function authMe() {
  return request('/auth/me')
}

export async function authClaimSessions(sessionIds) {
  return request('/auth/claim-sessions', {
    method: 'POST',
    body: JSON.stringify({ session_ids: sessionIds }),
  })
}

// --- Consultation Sessions (public) ---

export async function getConsultSessions() {
  return request('/consult/sessions')
}

export async function createConsultSession(title = 'New Consultation') {
  return request('/consult/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function getConsultSession(id) {
  return request(`/consult/sessions/${id}`)
}

export async function deleteConsultSession(id) {
  return request(`/consult/sessions/${id}`, {
    method: 'DELETE',
  })
}

export async function sendConsultMessage(sessionId, content, { forceTransition = false } = {}) {
  return request(`/consult/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, force_transition: forceTransition }),
  })
}

/**
 * Stream a consultation message response via SSE.
 *
 * @param {string} sessionId
 * @param {string} content
 * @param {Object} options
 * @param {boolean} options.forceTransition
 * @param {Object} callbacks
 * @param {function} callbacks.onStatus   — { message }
 * @param {function} callbacks.onMetadata — { phase, application_domain?, ... }
 * @param {function} callbacks.onChunk    — { text }
 * @param {function} callbacks.onSection  — { section } — emitted when report section starts
 * @param {function} callbacks.onComplete — { phase, application_domain?, full_report? }
 * @param {function} callbacks.onError    — Error
 */
export async function sendConsultMessageStream(
  sessionId,
  content,
  { forceTransition = false } = {},
  callbacks = {},
) {
  const { onStatus, onMetadata, onChunk, onSection, onComplete, onError } = callbacks

  try {
    const authToken = getAuthToken()
    const headers = { 'Content-Type': 'application/json' }
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`
    }

    const res = await fetch(`${BASE}/consult/sessions/${sessionId}/messages/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ content, force_transition: forceTransition }),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Request failed: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Parse SSE lines
      const lines = buffer.split('\n')
      buffer = ''
      let currentEvent = null

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ') && currentEvent) {
          try {
            const data = JSON.parse(line.slice(6))
            switch (currentEvent) {
              case 'status':
                onStatus?.(data)
                break
              case 'metadata':
                onMetadata?.(data)
                break
              case 'chunk':
                onChunk?.(data)
                break
              case 'section':
                onSection?.(data)
                break
              case 'complete':
                onComplete?.(data)
                break
              case 'error':
                onError?.(new Error(data.message || 'Streaming error'))
                break
            }
          } catch {
            // Incomplete JSON — put back in buffer
            buffer = `event: ${currentEvent}\n${line}\n`
          }
          currentEvent = null
        } else if (line === '') {
          currentEvent = null
        } else {
          buffer += line + '\n'
        }
      }
    }
  } catch (err) {
    onError?.(err)
  }
}

export async function submitConsultFeedback(sessionId, rating, comment = '') {
  return request(`/consult/sessions/${sessionId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment }),
  })
}

// --- Consultation Outcomes ---

export async function getConsultOutcomes(sessionId) {
  return request(`/consult/sessions/${sessionId}/outcomes`)
}

export async function submitConsultOutcome(sessionId, data) {
  return request(`/consult/sessions/${sessionId}/outcomes`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateConsultOutcome(sessionId, outcomeId, data) {
  return request(`/consult/sessions/${sessionId}/outcomes/${outcomeId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// --- Invention Sessions (private) ---

function getInventToken() {
  return sessionStorage.getItem('invent_token') || ''
}

export function setInventToken(passphrase) {
  sessionStorage.setItem('invent_token', passphrase)
}

export function clearInventToken() {
  sessionStorage.removeItem('invent_token')
}

export function hasInventToken() {
  return !!sessionStorage.getItem('invent_token')
}

function inventRequest(url, options = {}) {
  const token = getInventToken()
  return request(url, {
    ...options,
    headers: {
      ...options.headers,
      'X-Invent-Token': token,
    },
  })
}

export async function inventAuth(passphrase) {
  return request('/invent/auth', {
    method: 'POST',
    body: JSON.stringify({ passphrase }),
  })
}

export async function getInventSessions() {
  return inventRequest('/invent/sessions')
}

export async function createInventSession(title = 'New Session') {
  return inventRequest('/invent/sessions', {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
}

export async function getInventSession(id) {
  return inventRequest(`/invent/sessions/${id}`)
}

export async function deleteInventSession(id) {
  return inventRequest(`/invent/sessions/${id}`, {
    method: 'DELETE',
  })
}

export async function sendInventMessage(sessionId, content) {
  return inventRequest(`/invent/sessions/${sessionId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}
