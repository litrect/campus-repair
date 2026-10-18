// Browser ES module example. Pass your own token store and UI session-expiry handler.
export class ApiError extends Error {
  constructor(message, status = 0, code = status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export function createApi({ baseUrl = 'http://127.0.0.1:5000', getToken = () => null, onUnauthorized = () => {} } = {}) {
  const base = baseUrl.replace(/\/$/, '');
  async function request(path, { method = 'GET', query = {}, body, headers = {}, blob = false, anonymous = false, signal } = {}) {
    // Do not send bearer credentials to arbitrary URLs supplied by user input.
    if (!path.startsWith('/api/') || path.includes('..') || path.includes('?') || path.includes('#')) {
      throw new ApiError('无效的 API 路径');
    }
    const url = new URL(base + path);
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
    }
    const requestHeaders = new Headers(headers);
    const token = getToken();
    if (!anonymous && token) requestHeaders.set('Authorization', `Bearer ${token}`);
    if (body !== undefined && !(body instanceof FormData)) {
      requestHeaders.set('Content-Type', 'application/json');
      body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(url, { method, headers: requestHeaders, body, signal });
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      throw new ApiError('网络请求失败，请检查后端是否启动');
    }
    if (blob && response.ok) return response.blob();
    let payload;
    try { payload = await response.json(); }
    catch { throw new ApiError('服务返回了无法解析的响应', response.status); }
    if (!response.ok || payload.code !== 0) {
      if (response.status === 401 && !anonymous) onUnauthorized();
      throw new ApiError(payload.message || '请求失败', response.status, payload.code);
    }
    return payload.data;
  }
  return {
    request,
    login: (username, password) => request('/api/auth/login', { method: 'POST', body: { username, password }, anonymous: true }),
    options: () => request('/api/meta/order-options'),
    createOrder: (input, idempotencyKey) => request('/api/orders', { method: 'POST', body: input, headers: { 'Idempotency-Key': idempotencyKey } }),
    uploadImage: file => { const form = new FormData(); form.append('file', file); return request('/api/uploads/images', { method: 'POST', body: form }); },
    imageBlob: imageUrl => request(imageUrl, { blob: true }),
    detail: id => request(`/api/orders/${encodeURIComponent(id)}`),
    logs: id => request(`/api/orders/${encodeURIComponent(id)}/logs`),
    myOrders: query => request('/api/orders/my', { query }),
    assignedOrders: query => request('/api/orders/assigned-to-me', { query }),
    pending: query => request('/api/orders/pending', { query }),
    workers: category => request('/api/workers/available', { query: { category } }),
    action: (id, action, input) => {
      if (!['assign', 'accept', 'finish', 'confirm', 'reject', 'cancel', 'evaluate'].includes(action)) throw new ApiError('未知操作');
      return request(`/api/orders/${encodeURIComponent(id)}/${action}`, { method: 'POST', body: input });
    },
    evaluations: query => request('/api/stats/evaluations', { query }),
    statistics: query => request('/api/stats/orders', { query }),
    overtime: query => request('/api/orders/overtime', { query }),
  };
}
