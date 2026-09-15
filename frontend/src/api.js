const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000').replace(/\/$/, '')
const CSRF_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function buildUrl(path) {
  return path.startsWith('http://') || path.startsWith('https://')
    ? path
    : `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

function isJsonBody(body) {
  return Array.isArray(body) || Object.prototype.toString.call(body) === '[object Object]'
}

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || ''

  if (!contentType.includes('application/json')) {
    return null
  }

  return response.json().catch(() => null)
}

async function getCsrfToken() {
  const response = await fetch(buildUrl('/api/auth/csrf'), {
    credentials: 'include',
  })
  const payload = await parseResponse(response)

  if (!response.ok || !payload?.data?.csrf_token) {
    const error = new Error(payload?.error?.message || 'Unable to obtain a CSRF token.')
    error.status = response.status
    throw error
  }

  return payload.data.csrf_token
}

export async function apiRequest(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  let body = options.body

  if (isJsonBody(body)) {
    body = JSON.stringify(body)
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
  }

  if (CSRF_METHODS.has(method) && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', await getCsrfToken())
  }

  const response = await fetch(buildUrl(path), {
    ...options,
    method,
    headers,
    body,
    credentials: 'include',
  })
  const payload = await parseResponse(response)

  if (!response.ok) {
    const error = new Error(payload?.error?.message || `Request failed with status ${response.status}.`)
    error.status = response.status
    error.code = payload?.error?.code
    error.details = payload?.error?.details
    throw error
  }

  return payload
}

export async function getCurrentUser() {
  const payload = await apiRequest('/api/auth/me')
  return payload.data.user
}

export async function login(credentials) {
  const payload = await apiRequest('/api/auth/login', {
    method: 'POST',
    body: credentials,
  })
  return payload.data.user
}

export function logout() {
  return apiRequest('/api/auth/logout', { method: 'POST' })
}

export function changePassword(passwords) {
  return apiRequest('/api/auth/change-password', {
    method: 'POST',
    body: passwords,
  })
}