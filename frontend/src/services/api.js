const API_BASE = '/api';
const TOKEN_KEY = 'auth_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function isAuthenticated() {
  return Boolean(getToken());
}

export async function apiRequest(path, options = {}) {
  const apiPath = path.startsWith('/api/') ? path : `${API_BASE}${path}`;
  const headers = new Headers(options.headers);
  const token = getToken();

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(apiPath, { ...options, headers });

  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event('auth:logout'));
    throw new Error('Your session expired. Please sign in again.');
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === 'string' ? payload.detail : null;
    throw new Error(detail || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

export async function getBackendMessage() {
  return apiRequest('/health');
}

export async function checkHealth() {
  try {
    await apiRequest('/health');
    return true;
  } catch {
    return false;
  }
}

export async function login(payload) {
  const token = await apiRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  setToken(token.access_token);

  try {
    const user = await apiRequest('/auth/me');
    return { token: token.access_token, user };
  } catch (error) {
    setToken(null);
    throw error;
  }
}

export async function register(payload) {
  await apiRequest('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  return login({ email: payload.email, password: payload.password });
}

export async function getCurrentUser() {
  return apiRequest('/auth/me');
}

export function logout() {
  setToken(null);
}

export function detectFrame(blob, language = 'en') {
  const form = new FormData();
  form.append('image', blob, 'frame.jpg');

  return apiRequest(`/detect?language=${encodeURIComponent(language)}`, {
    method: 'POST',
    body: form,
  });
}

export async function fetchSpeechAudioUrl(text, language = 'en') {
  const headers = new Headers();
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const query = new URLSearchParams({ text, language });
  const response = await fetch(`${API_BASE}/tts?${query}`, { headers });
  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event('auth:logout'));
    throw new Error('Your session expired. Please sign in again.');
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = typeof payload.detail === 'string' ? payload.detail : null;
    throw new Error(detail || `Speech request failed with status ${response.status}`);
  }

  const audio = await response.blob();
  if (audio.size === 0) {
    throw new Error('Speech provider returned empty audio.');
  }
  return {
    url: URL.createObjectURL(audio),
    provider: response.headers.get('X-TTS-Provider') || 'unknown',
  };
}

export function getHistory(limit = 20) {
  return apiRequest(`/detections?limit=${encodeURIComponent(limit)}`);
}

export function getStats() {
  return apiRequest('/detections/stats');
}

export function clearHistory() {
  return apiRequest('/detections', { method: 'DELETE' });
}

export function createDetection(payload) {
  return apiRequest('/detections', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createDetectionBatch(payloads) {
  return apiRequest('/detections/batch', {
    method: 'POST',
    body: JSON.stringify(payloads),
  });
}