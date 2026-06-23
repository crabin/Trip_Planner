<script setup lang="ts">
import { message } from "ant-design-vue";
import axios from "axios";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed, ref } from "vue";

import { getDeepPlanItinerary, getReportItinerary } from "../services/api";
import type { Itinerary, TripDetailResponse } from "../types";

const props = defineProps<{ detail: TripDetailResponse | null }>();
const emit = defineEmits<{ backHome: []; viewHistory: []; openTrip: [itinerary: Itinerary] }>();

const activeTab = ref<"report" | "sources">("report");
const converting = ref(false);
const renderedMarkdown = computed(() => {
  const markdown = props.detail?.deep_plan?.markdown || "";
  return DOMPurify.sanitize(marked.parse(markdown, { async: false }) as string);
});

function conversionErrorMessage(error: unknown) {
  if (!axios.isAxiosError(error)) {
    return "深度规划转换为结果页失败，请稍后再试。";
  }
  if (error.code === "ECONNABORTED") {
    return "转换超时：已优先复用缓存，若仍超时请稍后再试。";
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return `转换失败：${detail}`;
  }
  if (error.response?.status) {
    return `转换失败：后端返回 ${error.response.status}。`;
  }
  return "转换失败：请检查前端到后端的连接。";
}

async function convertToResult() {
  if (!props.detail?.deep_plan) {
    return;
  }
  converting.value = true;
  try {
    const itinerary = props.detail.trip_id.startsWith("report_")
      ? await getReportItinerary(props.detail.trip_id)
      : await getDeepPlanItinerary(props.detail.trip_id);
    emit("openTrip", itinerary);
    message.success("已根据深度规划生成结果页。");
  } catch (error) {
    console.error(error);
    message.error(conversionErrorMessage(error));
  } finally {
    converting.value = false;
  }
}
</script>

<template>
  <section v-if="detail?.deep_plan" class="deep-page">
    <div class="deep-hero">
      <div>
        <span class="deep-hero__eyebrow">Destination Intelligence</span>
        <h2>{{ detail.display_title }}</h2>
        <p>{{ detail.detail_title }}</p>
      </div>
      <div class="deep-hero__actions">
        <button :disabled="converting" @click="convertToResult">
          {{ converting ? "转换中..." : "转换到结果页" }}
        </button>
        <button @click="$emit('backHome')">返回规划页</button>
        <button @click="$emit('viewHistory')">查看历史</button>
      </div>
    </div>

    <div class="deep-tabs">
      <button :class="{ active: activeTab === 'report' }" @click="activeTab = 'report'">
        完整攻略
      </button>
      <button :class="{ active: activeTab === 'sources' }" @click="activeTab = 'sources'">
        研究来源（{{ detail.deep_plan.sources.length }}）
      </button>
    </div>

    <article v-if="activeTab === 'report'" class="deep-panel markdown-body" v-html="renderedMarkdown"></article>
    <div v-else class="deep-panel source-list">
      <div v-if="detail.deep_plan.sources.length === 0" class="source-empty">
        本次研究没有返回可展示的引用信息。
      </div>
      <details v-for="(source, index) in detail.deep_plan.sources" :key="`${source.url}-${index}`" class="source-card">
        <summary>
          <span>{{ source.title || source.query || `来源 ${index + 1}` }}</span>
          <small>{{ source.section_title }}</small>
        </summary>
        <div class="source-card__content">
          <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>
          <p v-if="source.content">{{ source.content }}</p>
          <div class="source-card__meta">
            <span v-if="source.score != null">相关度：{{ source.score }}</span>
            <span v-if="source.published_date">来源发布日期：{{ source.published_date }}</span>
          </div>
        </div>
      </details>
    </div>
  </section>
</template>

<style scoped>
.deep-page { display: grid; gap: 18px; }
.deep-hero, .deep-panel, .deep-tabs { border-radius: 24px; background: rgba(255,255,255,.94); box-shadow: 0 22px 55px rgba(98,116,164,.12); }
.deep-hero { display: flex; justify-content: space-between; align-items: end; gap: 20px; padding: 28px; }
.deep-hero__eyebrow { color: #765cc5; font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.deep-hero h2 { margin: 8px 0; color: #31456a; font-size: 30px; }
.deep-hero p { margin: 0; color: #667085; }
.deep-hero__actions { display: flex; gap: 10px; }
.deep-hero__actions button, .deep-tabs button { border: 0; border-radius: 13px; padding: 11px 16px; color: #5f60c8; background: #eef0ff; font-weight: 700; cursor: pointer; }
.deep-tabs { display: flex; gap: 10px; padding: 8px; }
.deep-tabs button.active { color: #fff; background: linear-gradient(135deg, #7386e0, #8f71d8); }
.deep-panel { padding: 30px; overflow: hidden; }
.source-list { display: grid; gap: 12px; }
.source-card { border: 1px solid #e7e9f5; border-radius: 16px; background: #fbfbff; }
.source-card summary { display: grid; gap: 5px; padding: 16px 18px; color: #394867; font-weight: 700; cursor: pointer; }
.source-card summary small { color: #8a94a6; font-weight: 500; }
.source-card__content { padding: 0 18px 18px; color: #475467; line-height: 1.7; }
.source-card__content a { color: #6568cf; font-weight: 700; }
.source-card__meta { display: flex; flex-wrap: wrap; gap: 14px; color: #8a94a6; font-size: 12px; }
.source-empty { color: #667085; text-align: center; }
.markdown-body { color: #344054; line-height: 1.8; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: #31456a; line-height: 1.35; }
.markdown-body :deep(h1) { border-bottom: 1px solid #e6e9f5; padding-bottom: 14px; }
.markdown-body :deep(a) { color: #6267cc; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid #e1e5f0; padding: 9px 11px; text-align: left; }
.markdown-body :deep(blockquote) { margin-left: 0; border-left: 4px solid #8c80d9; padding-left: 14px; color: #667085; }
@media (max-width: 720px) { .deep-hero { align-items: stretch; flex-direction: column; } .deep-hero__actions { flex-wrap: wrap; } .deep-panel { padding: 20px; } }
</style>
