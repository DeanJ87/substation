export function csrfToken(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

export const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
