// getRandomValues is also available on HTTP origins; randomUUID requires a secure context.
export function createSubmissionKey(): string {
  const bytes = new Uint8Array(16)
  globalThis.crypto.getRandomValues(bytes)
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}
