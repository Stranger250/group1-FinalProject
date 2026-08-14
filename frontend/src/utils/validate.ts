/** 图片上传预校验（PRD B03：jpg/png/jpeg，单文件 ≤5MB）。返回错误文案，null 表示通过。 */
export function validateImage(file: File): string | null {
  const name = file.name || ''
  if (!/\.(jpg|jpeg|png)$/i.test(name)) {
    return `仅支持 jpg/png/jpeg 图片，当前文件：${name || '未知'}`
  }
  if (file.size > 5 * 1024 * 1024) {
    return `图片超过大小上限（5MB）：${(file.size / 1024 / 1024).toFixed(1)}MB`
  }
  return null
}
