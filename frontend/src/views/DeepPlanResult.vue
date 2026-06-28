<script setup lang="ts">
import { message } from "ant-design-vue";
import axios from "axios";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";

import { getDeepPlanItinerary, getReportItinerary } from "../services/api";
import type { DeepPlanResearchTraceStep, Itinerary, TripDetailResponse } from "../types";

const props = defineProps<{ detail: TripDetailResponse | null }>();
const emit = defineEmits<{ backHome: []; viewHistory: []; openTrip: [itinerary: Itinerary] }>();
const { t } = useI18n();

const activeTab = ref<"report" | "process" | "sources">("report");
const converting = ref(false);
const renderedMarkdown = computed(() => {
  const markdown = props.detail?.deep_plan?.markdown || "";
  return DOMPurify.sanitize(marked.parse(markdown, { async: false }) as string);
});
const researchTrace = computed(() => props.detail?.deep_plan?.research_trace || []);
const groupedTrace = computed(() => {
  const groups: { section: string; steps: DeepPlanResearchTraceStep[] }[] = [];
  for (const step of researchTrace.value) {
    const section = step.section_title || "-";
    let group = groups.find((item) => item.section === section);
    if (!group) {
      group = { section, steps: [] };
      groups.push(group);
    }
    group.steps.push(step);
  }
  return groups;
});

function conversionErrorMessage(error: unknown) {
  if (!axios.isAxiosError(error)) {
    return t("deepResult.messages.genericConversionFailed");
  }
  if (error.code === "ECONNABORTED") {
    return t("deepResult.messages.timeout");
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return t("deepResult.messages.detail", { detail });
  }
  if (
    detail &&
    typeof detail === "object" &&
    "message" in detail &&
    typeof detail.message === "string" &&
    detail.message.trim()
  ) {
    return t("deepResult.messages.detail", { detail: detail.message });
  }
  if (error.response?.status) {
    return t("deepResult.messages.status", { status: error.response.status });
  }
  return t("deepResult.messages.connection");
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
    message.success(t("deepResult.messages.success"));
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
        <span class="deep-hero__eyebrow">{{ t("deepResult.eyebrow") }}</span>
        <h2>{{ detail.display_title }}</h2>
        <p>{{ detail.detail_title }}</p>
      </div>
      <div class="deep-hero__actions">
        <button :disabled="converting" @click="convertToResult">
          {{ converting ? t("deepResult.converting") : t("deepResult.convert") }}
        </button>
        <button @click="$emit('backHome')">{{ t("deepResult.back") }}</button>
        <button @click="$emit('viewHistory')">{{ t("deepResult.history") }}</button>
      </div>
    </div>

    <div class="deep-tabs">
      <button :class="{ active: activeTab === 'report' }" @click="activeTab = 'report'">
        {{ t("deepResult.report") }}
      </button>
      <button :class="{ active: activeTab === 'process' }" @click="activeTab = 'process'">
        {{ t("deepResult.process", { count: researchTrace.length }) }}
      </button>
      <button :class="{ active: activeTab === 'sources' }" @click="activeTab = 'sources'">
        {{ t("deepResult.sources", { count: detail.deep_plan.sources.length }) }}
      </button>
    </div>

    <article v-if="activeTab === 'report'" class="deep-panel markdown-body" v-html="renderedMarkdown"></article>
    <div v-else-if="activeTab === 'process'" class="deep-panel process-list">
      <div v-if="researchTrace.length === 0" class="source-empty">
        {{ t("deepResult.emptyProcess") }}
      </div>
      <details v-for="group in groupedTrace" :key="group.section" class="process-section" open>
        <summary>{{ group.section }}</summary>
        <article v-for="step in group.steps" :key="step.step_id" class="process-step">
          <header>
            <strong>{{ step.phase || step.step_id }}</strong>
            <span>{{ t("deepResult.searchTool", { tool: step.search_tool || "-" }) }}</span>
          </header>
          <p v-if="step.search_query" class="process-step__query">{{ step.search_query }}</p>
          <p v-if="step.reasoning">{{ step.reasoning }}</p>
          <div class="source-card__meta">
            <span>{{ t("deepResult.evidenceCount", { count: step.evidence_count }) }}</span>
            <span>{{ t("deepResult.tokenEstimate", { tokens: step.estimated_prompt_tokens }) }}</span>
          </div>
          <p v-if="step.fallback_reason" class="process-step__fallback">
            {{ t("deepResult.fallbackReason", { reason: step.fallback_reason }) }}
          </p>
          <div class="process-step__summaries">
            <section v-if="step.summary_before">
              <small>{{ t("deepResult.summaryBefore") }}</small>
              <p>{{ step.summary_before }}</p>
            </section>
            <section v-if="step.summary_after">
              <small>{{ t("deepResult.summaryAfter") }}</small>
              <p>{{ step.summary_after }}</p>
            </section>
          </div>
        </article>
      </details>
    </div>
    <div v-else class="deep-panel source-list">
      <div v-if="detail.deep_plan.sources.length === 0" class="source-empty">
        {{ t("deepResult.emptySources") }}
      </div>
      <details v-for="(source, index) in detail.deep_plan.sources" :key="`${source.url}-${index}`" class="source-card">
        <summary>
          <span>{{ source.title || source.query || t("deepResult.sourceFallback", { index: index + 1 }) }}</span>
          <small>{{ source.section_title }}</small>
        </summary>
        <div class="source-card__content">
          <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ t("deepResult.openSource") }}</a>
          <p v-if="source.content">{{ source.content }}</p>
          <p v-if="source.raw_content && source.raw_content !== source.content">{{ source.raw_content }}</p>
          <div class="source-card__meta">
            <span>{{ source.used_in_summary ? t("deepResult.usedInSummary") : t("deepResult.notUsedInSummary") }}</span>
            <span v-if="source.step_id">{{ source.step_id }}</span>
            <span v-if="source.score != null">{{ t("deepResult.relevance", { score: source.score }) }}</span>
            <span v-if="source.published_date">{{ t("deepResult.published", { date: source.published_date }) }}</span>
          </div>
        </div>
      </details>
    </div>
  </section>
</template>

<style scoped>
.deep-page { display: grid; gap: 20px; }
.deep-hero, .deep-panel, .deep-tabs {
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.92), rgba(250,251,247,.86));
  box-shadow: 0 22px 55px rgba(34, 61, 57, 0.08);
}
.deep-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, max-content);
  align-items: end;
  gap: 20px;
  padding: 28px;
  background:
    linear-gradient(135deg, rgba(255,255,255,.9), rgba(240,246,242,.84)),
    radial-gradient(circle at 92% 0%, rgba(215,173,88,.16), transparent 30%);
}
.deep-hero > div:first-child {
  min-width: 0;
}
.deep-hero__eyebrow { color: #8f661f; font-size: 12px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
.deep-hero h2 { margin: 8px 0; color: #143c38; font-size: 30px; line-height: 1.2; }
.deep-hero p { margin: 0; color: #63726e; }
.deep-hero__actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(96px, 1fr));
  gap: 10px;
  width: min(100%, 396px);
  justify-self: end;
}
.deep-hero__actions button, .deep-tabs button {
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 13px;
  padding: 11px 16px;
  color: #143c38;
  background: rgba(238, 246, 241, 0.9);
  font-weight: 800;
  line-height: 1.2;
  white-space: nowrap;
  cursor: pointer;
}
.deep-hero__actions button:first-child {
  border-color: rgba(215, 173, 88, 0.3);
  background: linear-gradient(135deg, #d7ad58, #c9983d);
  color: #241b0c;
}
.deep-tabs { display: flex; gap: 10px; padding: 8px; }
.deep-tabs button.active { color: #fff; background: linear-gradient(135deg, #143c38, #1f574f); }
.deep-panel { padding: 30px; overflow: hidden; }
.source-list { display: grid; gap: 12px; }
.source-card, .process-section {
  border: 1px solid rgba(25, 66, 63, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.76);
}
.source-card summary { display: grid; gap: 5px; padding: 16px 18px; color: #143c38; font-weight: 800; cursor: pointer; }
.source-card summary small { color: #63726e; font-weight: 600; }
.source-card__content { padding: 0 18px 18px; color: #314844; line-height: 1.7; }
.source-card__content a { color: #8f661f; font-weight: 800; }
.source-card__meta { display: flex; flex-wrap: wrap; gap: 14px; color: #63726e; font-size: 12px; }
.source-empty { color: #63726e; text-align: center; }
.process-list { display: grid; gap: 14px; }
.process-section > summary { padding: 16px 18px; color: #143c38; font-weight: 900; cursor: pointer; }
.process-step { margin: 0 18px 16px; padding: 14px; border: 1px solid rgba(25, 66, 63, 0.1); border-radius: 12px; background: rgba(255,255,255,.9); color: #314844; }
.process-step header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; color: #143c38; }
.process-step p { margin: 8px 0 0; line-height: 1.65; }
.process-step__query { color: #8f661f; font-weight: 800; }
.process-step__fallback { color: #b54708; }
.process-step__summaries { display: grid; gap: 10px; margin-top: 12px; }
.process-step__summaries section { padding: 10px 12px; border-radius: 10px; background: rgba(238,246,241,.74); }
.process-step__summaries small { color: #8f661f; font-weight: 900; }
.markdown-body { color: #314844; line-height: 1.8; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: #143c38; line-height: 1.35; }
.markdown-body :deep(h1) { border-bottom: 1px solid rgba(25, 66, 63, 0.12); padding-bottom: 14px; }
.markdown-body :deep(a) { color: #8f661f; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { border: 1px solid rgba(25, 66, 63, 0.12); padding: 9px 11px; text-align: left; }
.markdown-body :deep(th) { background: rgba(20, 60, 56, 0.08); color: #143c38; }
.markdown-body :deep(blockquote) { margin-left: 0; border-left: 4px solid #d7ad58; padding-left: 14px; color: #63726e; }
@media (max-width: 900px) {
  .deep-hero {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
  .deep-hero__actions {
    width: 100%;
    justify-self: stretch;
  }
}
@media (max-width: 720px) {
  .deep-hero__actions {
    grid-template-columns: 1fr;
  }
  .deep-panel {
    padding: 20px;
  }
}
</style>
