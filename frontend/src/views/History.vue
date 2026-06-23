<script setup lang="ts">
import { message } from "ant-design-vue";
import { onMounted, onUnmounted, ref, watch } from "vue";

import {
  deleteTrip,
  getDeepPlanItinerary,
  getReportItinerary,
  getTripDetail,
  getTripReport,
  listTrips,
} from "../services/api";
import type { Itinerary, TripDetailResponse, TripSummaryItem } from "../types";

const props = defineProps<{ active: boolean }>();

const emit = defineEmits<{
  openTrip: [itinerary: Itinerary];
  openDeepPlan: [detail: TripDetailResponse];
}>();

const loading = ref(false);
const items = ref<TripSummaryItem[]>([]);
const deletingTripId = ref("");
let pollingTimer: number | undefined;

function normalizeCardText(value?: string | null) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function formatStatus(status: TripSummaryItem["status"]) {
  if (status === "generating") {
    return "正在生成";
  }
  if (status === "failed") {
    return "生成失败";
  }
  return "已完成";
}

function cardDetailTitle(item: TripSummaryItem) {
  const detailTitle = normalizeCardText(item.detail_title);
  const summary = normalizeCardText(item.summary);
  if (detailTitle && detailTitle !== summary) {
    return item.detail_title;
  }

  const dateRange =
    item.start_date && item.end_date
      ? `${item.start_date} 至 ${item.end_date}`
      : item.start_date || item.end_date || "";
  return [dateRange, item.plan_type === "deep" ? "深度规划" : "快速规划", formatStatus(item.status)]
    .filter(Boolean)
    .join(" · ");
}

function stopPolling() {
  if (pollingTimer !== undefined) {
    window.clearTimeout(pollingTimer);
    pollingTimer = undefined;
  }
}

function schedulePolling() {
  stopPolling();
  if (!props.active || !items.value.some((item) => item.status === "generating")) {
    return;
  }
  pollingTimer = window.setTimeout(async () => {
    await loadTrips(false);
  }, 2200);
}

async function loadTrips(showLoading = true) {
  if (showLoading) {
    loading.value = true;
  }
  try {
    const response = await listTrips();
    items.value = response.items;
  } catch (error) {
    console.error(error);
    if (showLoading) {
      message.error("历史列表加载失败。");
    }
  } finally {
    loading.value = false;
    schedulePolling();
  }
}

async function openTrip(item: TripSummaryItem) {
  if (!item.has_detail) {
    return;
  }
  try {
    if (item.has_itinerary) {
      const response = await getTripDetail(item.trip_id);
      if (response.itinerary) {
        emit("openTrip", response.itinerary);
        message.success("已加载已保存行程。");
      }
      return;
    }

    if (item.report_id) {
      const itinerary = await getReportItinerary(item.report_id);
      emit("openTrip", itinerary);
      message.success("已根据 Report 生成结果页。");
      return;
    }

    if (item.plan_type === "deep") {
      const itinerary = await getDeepPlanItinerary(item.trip_id);
      emit("openTrip", itinerary);
      message.success("已根据深度规划生成结果页。");
      return;
    }

    const response = await getTripDetail(item.trip_id);
    if (response.itinerary) {
      emit("openTrip", response.itinerary);
      message.success("已加载已保存行程。");
    }
  } catch (error) {
    console.error(error);
    message.error("读取行程详情失败。");
  }
}

async function openReport(item: TripSummaryItem) {
  if (!item.has_report || !item.report_id) {
    return;
  }
  try {
    const response = await getTripReport(item.report_id);
    emit("openDeepPlan", response);
    message.success("已加载深度规划 Report。");
  } catch (error) {
    console.error(error);
    message.error("读取 Report 失败。");
  }
}

async function removeTrip(item: TripSummaryItem) {
  if (item.status === "generating") {
    return;
  }
  const confirmed = window.confirm("确定要删除这条行程吗？删除后无法恢复。");
  if (!confirmed) {
    return;
  }

  deletingTripId.value = item.trip_id;
  try {
    await deleteTrip(item.trip_id);
    items.value = items.value.filter((entry) => entry.trip_id !== item.trip_id);
    message.success("行程已删除。");
  } catch (error) {
    console.error(error);
    message.error("删除行程失败。");
  } finally {
    deletingTripId.value = "";
    schedulePolling();
  }
}

onMounted(() => {
  if (props.active) {
    void loadTrips();
  }
});

watch(
  () => props.active,
  (active) => {
    if (active) {
      void loadTrips();
    } else {
      stopPolling();
    }
  }
);

onUnmounted(stopPolling);
</script>

<template>
  <section class="history-page">
    <div class="history-header">
      <div>
        <h2>历史行程</h2>
        <p>快速行程与深度规划会统一显示在这里。</p>
      </div>
      <button class="refresh-button" @click="loadTrips()">刷新列表</button>
    </div>

    <div v-if="loading" class="history-state">正在加载历史列表...</div>
    <div v-else-if="items.length === 0" class="history-state">还没有已保存的行程。</div>

    <div v-else class="history-grid">
      <article v-for="item in items" :key="item.trip_id" class="history-card">
        <div class="history-card__topline">
          <span class="history-card__kind">
            {{ item.plan_type === "deep" ? "深度规划" : "快速规划" }}
          </span>
          <span :class="['history-card__status', `history-card__status--${item.status}`]">
            {{ item.status === "generating" ? "正在生成" : item.status === "failed" ? "生成失败" : "已完成" }}
          </span>
        </div>
        <div class="history-card__destination">
          {{ item.display_title || item.destination }}
        </div>
        <div class="history-card__trip-id">
          {{ cardDetailTitle(item) || item.trip_id }}
        </div>

        <div v-if="item.status === 'generating'" class="history-card__progress">
          <a-progress :percent="item.progress" status="active" />
          <p>{{ item.summary }}</p>
        </div>
        <div v-else-if="item.status === 'failed'" class="history-card__progress">
          <a-progress :percent="item.progress" status="exception" />
          <p>{{ item.error_message || item.summary }}</p>
        </div>
        <p v-else class="history-card__summary">{{ item.summary }}</p>

        <div class="history-card__time">更新时间：{{ item.updated_at || "未记录" }}</div>
        <div
          :class="[
            'history-card__actions',
            { 'history-card__actions--three': item.has_report }
          ]"
        >
          <button
            class="history-card__button"
            :disabled="!item.has_detail"
            @click="openTrip(item)"
          >
            查看详情
          </button>
          <button
            v-if="item.has_report"
            class="history-card__button history-card__button--report"
            @click="openReport(item)"
          >
            查看 Report
          </button>
          <button
            class="history-card__button history-card__button--danger"
            :disabled="item.status === 'generating' || deletingTripId === item.trip_id"
            @click="removeTrip(item)"
          >
            {{ deletingTripId === item.trip_id ? "删除中..." : "删除行程" }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.history-page { display: grid; gap: 18px; }
.history-header { display: flex; justify-content: space-between; align-items: end; gap: 16px; padding: 24px; border-radius: 24px; background: rgba(255, 255, 255, 0.92); box-shadow: 0 22px 55px rgba(98, 116, 164, 0.12); }
.history-header h2 { margin: 0 0 8px; font-size: 28px; color: #31456a; }
.history-header p { margin: 0; color: #667085; }
.refresh-button, .history-card__button { border: none; border-radius: 14px; padding: 12px 16px; background: linear-gradient(135deg, #7386e0 0%, #8f71d8 100%); color: #fff; font-weight: 700; cursor: pointer; }
.history-state { padding: 28px; border-radius: 24px; background: rgba(255,255,255,.92); box-shadow: 0 22px 55px rgba(98,116,164,.12); color: #667085; text-align: center; }
.history-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(310px, 1fr)); gap: 18px; }
.history-card { display: grid; gap: 12px; padding: 22px; border-radius: 24px; background: rgba(255,255,255,.92); box-shadow: 0 22px 55px rgba(98,116,164,.12); }
.history-card__topline { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.history-card__kind { color: #725cc1; font-size: 12px; font-weight: 800; letter-spacing: .04em; }
.history-card__status { padding: 5px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.history-card__status--generating { background: #eef2ff; color: #5b67cb; }
.history-card__status--completed { background: #ecfdf3; color: #14804a; }
.history-card__status--failed { background: #fff1f2; color: #c2414b; }
.history-card__destination { font-size: 24px; font-weight: 800; color: #42558d; }
.history-card__trip-id { min-height: 34px; color: #8a94a6; font-size: 13px; line-height: 1.5; }
.history-card__summary, .history-card__progress p { margin: 0; color: #475467; line-height: 1.7; }
.history-card__summary { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 6; }
.history-card__time { color: #667085; font-size: 13px; }
.history-card__actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.history-card__actions--three { grid-template-columns: repeat(3, 1fr); }
.history-card__button--report { background: linear-gradient(135deg, #7259bd, #a062c7); }
.history-card__button--danger { background: rgba(239,68,68,.12); color: #c2410c; }
.history-card__button:disabled { opacity: .52; cursor: not-allowed; }
@media (max-width: 640px) { .history-header { align-items: stretch; flex-direction: column; } .history-card__actions--three { grid-template-columns: 1fr; } }
</style>
