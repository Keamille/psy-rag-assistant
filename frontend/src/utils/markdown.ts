/**
 * Markdown 渲染与引用角标（开发文档 11.6）。
 *
 * AI 输出属于不可信内容，必须经过 DOMPurify 净化后才能 v-html。
 */

import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang }).value}</code></pre>`
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
  },
})

/** 把 [1] [2] 渲染为可点击角标；越界编号保持原样（与后端引用校验呼应） */
function decorateCitations(content: string, sourceCount: number): string {
  return content.replace(/\[(\d+)\]/g, (match, num: string) => {
    const index = Number(num)
    if (index >= 1 && index <= sourceCount) {
      return `<button type="button" class="cite-ref" data-cite="${index}">${index}</button>`
    }
    return match
  })
}

export function renderMarkdown(content: string, sourceCount = 0): string {
  const withCitations = decorateCitations(content, sourceCount)
  const html = md.render(withCitations)
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ['data-cite', 'target', 'rel'],
    ADD_TAGS: ['button'],
  })
}

/** 纯文本预览（会话列表、来源片段等场景，不做任何 HTML 解析） */
export function plainPreview(text: string, limit = 40): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat
}

