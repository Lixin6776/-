/** 聊天发图共用工具（主聊天框 / 直播运营助手都用）。 */

export const MAX_CHAT_IMAGES = 4;

export function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export type PickedImage = { name: string; dataUrl: string };

/** 从选中/粘贴的文件里挑出图片（最多 limit 张），过滤非图片。 */
export async function pickImages(
  files: FileList | File[] | null,
  limit: number
): Promise<PickedImage[]> {
  if (!files) return [];
  const picked: PickedImage[] = [];
  for (const file of Array.from(files)) {
    if (picked.length >= limit) break;
    if (!file.type.startsWith("image/")) continue;
    try {
      picked.push({ name: file.name || "图片", dataUrl: await readAsDataUrl(file) });
    } catch {
      /* 读不出来就跳过 */
    }
  }
  return picked;
}
