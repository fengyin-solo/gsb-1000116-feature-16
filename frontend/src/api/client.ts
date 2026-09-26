/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** 从 FastAPI 错误体里提炼可读原因：400/404 是字符串 detail，422 是数组。 */
export function extractErrorDetail(body: unknown): string {
  if (!body || typeof body !== 'object') {
    return ''
  }
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === 'object' ? String((item as { msg?: unknown }).msg ?? '') : ''))
      .filter(Boolean)
      .join('；')
  }
  return ''
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init)
  if (!response.ok) {
    let detail = ''
    try {
      detail = extractErrorDetail(await response.json())
    } catch {
      // 错误体不是 JSON 时只保留状态码
    }
    throw new Error(detail ? `接口返回 ${response.status}：${detail}` : `接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
