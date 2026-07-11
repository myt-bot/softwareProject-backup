// 把 AI 返回的 Markdown 渲染成安全的 HTML（供聊天面板 v-html 使用）。
// 用 marked 解析（开启 GFM，支持表格/列表/加粗等），再用 DOMPurify 净化，避免 XSS。
import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: true });

export function renderMarkdown(src: string): string {
  if (!src) return "";
  try {
    const raw = marked.parse(src, { async: false }) as string;
    return DOMPurify.sanitize(raw);
  } catch {
    // 解析失败就退回纯文本（保留换行），至少不报错、不丢内容
    return DOMPurify.sanitize(src.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>"));
  }
}
