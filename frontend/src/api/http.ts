export class ApiError extends Error {
  constructor(message: string, public status: number, public detail?: unknown) { super(message) }
}

async function responseError(response: Response) {
  let detail: unknown
  try { detail = await response.json() } catch { detail = null }
  const value = detail && typeof detail === 'object' && 'detail' in detail ? (detail as {detail?: unknown}).detail : detail
  const message = typeof value === 'string' ? value : response.status === 404 ? '请求的内容不存在' : response.status === 409 ? '当前状态暂时不能完成此操作' : response.status === 422 ? '请检查提交内容' : '服务暂时不可用，请稍后重试'
  return new ApiError(message, response.status, detail)
}

export async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) throw await responseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => requestJson<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => requestJson<T>(path, { method: 'POST', body: body == null ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) => requestJson<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => requestJson<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) => requestJson<T>(path, { method: 'POST', body: form })
}
