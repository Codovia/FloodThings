// Prepares a gallery photo for the server limits (backend/app/report_images.py).
// Photos that already fit are sent unchanged, so their embedded capture time/GPS can still be
// extracted with consent. Only oversized photos are redrawn smaller, which removes that metadata.
export const MAX_BYTES = 5 * 1024 * 1024
export const MAX_PIXELS = 10000000
export const MAX_INPUT_BYTES = 30 * 1024 * 1024

export async function preparePhoto(file) {
  if (!['image/jpeg', 'image/png'].includes(file.type)) throw Error('Choose a JPEG or PNG photo.')
  if (file.size > MAX_INPUT_BYTES) throw Error('This photo is too large. Choose one under 30 MB.')
  let bitmap
  try { bitmap = await createImageBitmap(file) } catch { throw Error('This photo could not be opened. Try another photo.') }
  const { width, height } = bitmap
  if (width * height <= MAX_PIXELS && file.size <= MAX_BYTES) { bitmap.close?.(); return { blob: file, mime: file.type, resized: false, width, height } }
  const scale = Math.min(1, Math.sqrt(MAX_PIXELS / (width * height)))
  const w = Math.max(1, Math.floor(width * scale)), h = Math.max(1, Math.floor(height * scale))
  const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h
  canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h); bitmap.close?.()
  let quality = 0.9, blob = null
  while (quality >= 0.5) { blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', quality)); if (blob && blob.size <= MAX_BYTES) break; quality -= 0.1 }
  if (!blob || blob.size > MAX_BYTES) throw Error('This photo is too large even after shrinking. Try another photo.')
  return { blob, mime: 'image/jpeg', resized: true, width: w, height: h }
}

export function toBase64(blob) {
  return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(Error('Photo could not be read.')); reader.readAsDataURL(blob) })
}
