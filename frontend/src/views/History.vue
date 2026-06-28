<script setup lang="ts">
import { message } from "ant-design-vue";
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

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
const { t } = useI18n();

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
    return t("history.status.generating");
  }
  if (status === "failed") {
    return t("history.status.failed");
  }
  return t("history.status.completed");
}

function cardDetailTitle(item: TripSummaryItem) {
  const detailTitle = normalizeCardText(item.detail_title);
  const summary = normalizeCardText(item.summary);
  if (detailTitle && detailTitle !== summary) {
    return item.detail_title;
  }

  const dateRange =
    item.start_date && item.end_date
      ? t("history.dateRange", { start: item.start_date, end: item.end_date })
      : item.start_date || item.end_date || "";
  return [dateRange, item.plan_type === "deep" ? t("history.planType.deep") : t("history.planType.quick"), formatStatus(item.status)]
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
      message.error(t("history.messages.loadFailed"));
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
        message.success(t("history.messages.tripLoaded"));
      }
      return;
    }

    if (item.report_id) {
      const itinerary = await getReportItinerary(item.report_id);
      emit("openTrip", itinerary);
      message.success(t("history.messages.reportToResult"));
      return;
    }

    if (item.plan_type === "deep") {
      const itinerary = await getDeepPlanItinerary(item.trip_id);
      emit("openTrip", itinerary);
      message.success(t("history.messages.deepToResult"));
      return;
    }

    const response = await getTripDetail(item.trip_id);
    if (response.itinerary) {
      emit("openTrip", response.itinerary);
      message.success(t("history.messages.tripLoaded"));
    }
  } catch (error) {
    console.error(error);
    message.error(t("history.messages.detailFailed"));
  }
}

async function openReport(item: TripSummaryItem) {
  if (!item.has_report || !item.report_id) {
    return;
  }
  try {
    const response = await getTripReport(item.report_id);
    emit("openDeepPlan", response);
    message.success(t("history.messages.reportLoaded"));
  } catch (error) {
    console.error(error);
    message.error(t("history.messages.reportFailed"));
  }
}

async function removeTrip(item: TripSummaryItem) {
  if (item.status === "generating") {
    return;
  }
  const confirmed = window.confirm(t("history.confirmDelete"));
  if (!confirmed) {
    return;
  }

  deletingTripId.value = item.trip_id;
  try {
    await deleteTrip(item.trip_id);
    items.value = items.value.filter((entry) => entry.trip_id !== item.trip_id);
    message.success(t("history.messages.deleted"));
  } catch (error) {
    console.error(error);
    message.error(t("history.messages.deleteFailed"));
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
        <h2>{{ t("history.title") }}</h2>
        <p>{{ t("history.description") }}</p>
      </div>
      <button class="refresh-button" @click="loadTrips()">{{ t("history.refresh") }}</button>
    </div>

    <div v-if="loading" class="history-state">{{ t("history.loading") }}</div>
    <div v-else-if="items.length === 0" class="history-state">{{ t("history.empty") }}</div>

    <div v-else class="history-grid">
      <article v-for="item in items" :key="item.trip_id" class="history-card">
        <div class="history-card__topline">
          <span class="history-card__kind">
            {{ item.plan_type === "deep" ? t("history.planType.deep") : t("history.planType.quick") }}
          </span>
          <span :class="['history-card__status', `history-card__status--${item.status}`]">
            {{ formatStatus(item.status) }}
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

        <div class="history-card__time">
          {{ t("history.updatedAt", { time: item.updated_at || t("history.unknownTime") }) }}
        </div>
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
            {{ t("history.actions.detail") }}
          </button>
          <button
            v-if="item.has_report"
            class="history-card__button history-card__button--report"
            @click="openReport(item)"
          >
            {{ t("history.actions.report") }}
          </button>
          <button
            class="history-card__button history-card__button--danger"
            :disabled="item.status === 'generating' || deletingTripId === item.trip_id"
            @click="removeTrip(item)"
          >
            {{ deletingTripId === item.trip_id ? t("history.actions.deleting") : t("history.actions.delete") }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.history-page {
  display: grid;
  gap: 20px;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 28px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 24px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(240, 246, 242, 0.84)),
    radial-gradient(circle at 92% 0%, rgba(215, 173, 88, 0.16), transparent 30%);
  box-shadow: 0 24px 64px rgba(34, 61, 57, 0.1);
}

.history-header h2 {
  margin: 0 0 8px;
  color: #173936;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 30px;
  line-height: 1.2;
}

.history-header p {
  margin: 0;
  color: #63726e;
  line-height: 1.6;
}

.refresh-button,
.history-card__button {
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 14px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #143c38, #1f574f);
  color: #ffffff;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 14px 28px rgba(20, 60, 56, 0.16);
}

.refresh-button:hover,
.history-card__button:hover {
  background: linear-gradient(135deg, #1f574f, #143c38);
}

.history-state {
  padding: 28px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 22px 55px rgba(34, 61, 57, 0.08);
  color: #63726e;
  text-align: center;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
  gap: 18px;
}

.history-card {
  position: relative;
  display: grid;
  gap: 12px;
  overflow: hidden;
  padding: 22px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(250, 251, 247, 0.84));
  box-shadow: 0 22px 55px rgba(34, 61, 57, 0.08);
}

.history-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, #173936, #d7ad58);
}

.history-card__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.history-card__kind {
  color: #8f661f;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.06em;
}

.history-card__status {
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.history-card__status--generating {
  background: rgba(215, 173, 88, 0.16);
  color: #8f661f;
}

.history-card__status--completed {
  background: rgba(20, 60, 56, 0.1);
  color: #143c38;
}

.history-card__status--failed {
  background: rgba(194, 65, 12, 0.1);
  color: #c2410c;
}

.history-card__destination {
  color: #143c38;
  font-size: 24px;
  font-weight: 900;
  line-height: 1.15;
}

.history-card__trip-id {
  min-height: 34px;
  color: #63726e;
  font-size: 13px;
  line-height: 1.5;
}

.history-card__summary,
.history-card__progress p {
  margin: 0;
  color: #314844;
  line-height: 1.7;
}

.history-card__summary {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
}

.history-card__time {
  color: #63726e;
  font-size: 13px;
}

.history-card__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.history-card__actions--three {
  grid-template-columns: repeat(3, 1fr);
}

.history-card__button--report {
  background: linear-gradient(135deg, #d7ad58, #c9983d);
  color: #241b0c;
}

.history-card__button--report:hover {
  background: linear-gradient(135deg, #c9983d, #d7ad58);
}

.history-card__button--danger {
  border-color: rgba(194, 65, 12, 0.12);
  background: rgba(194, 65, 12, 0.1);
  color: #c2410c;
  box-shadow: none;
}

.history-card__button:disabled {
  opacity: 0.52;
  cursor: not-allowed;
}

:deep(.ant-progress-bg) {
  background: #143c38 !important;
}

@media (max-width: 640px) {
  .history-header {
    align-items: stretch;
    flex-direction: column;
  }

  .history-card__actions--three {
    grid-template-columns: 1fr;
  }
}
</style>
