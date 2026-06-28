<script setup lang="ts">
import axios from "axios";
import { computed, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { useI18n } from "vue-i18n";

import {
  checkDestinationSpan,
  fetchLocationSuggestions,
  generateDeepTrip,
  generateTrip,
} from "../services/api";
import type {
  DestinationSpanCheckResponse,
  Itinerary,
  LocationSuggestion,
  TripRequestPayload,
  TripSummaryItem,
} from "../types";

const emit = defineEmits<{
  generated: [itinerary: Itinerary];
  deepSubmitted: [item: TripSummaryItem];
}>();

const { t } = useI18n();

const preferenceOptions = computed(() => [
  { label: t("home.optionLabels.nature"), value: "自然风景" },
  { label: t("home.optionLabels.photo"), value: "拍照" },
  { label: t("home.optionLabels.food"), value: "美食" },
  { label: t("home.optionLabels.oldTown"), value: "古镇" },
  { label: t("home.optionLabels.leisure"), value: "休闲" },
]);

const dietaryOptions = computed(() => [
  { label: t("home.optionLabels.mildSpice"), value: "少辣" },
  { label: t("home.optionLabels.noCilantro"), value: "不吃香菜" },
  { label: t("home.optionLabels.noScallion"), value: "不吃葱" },
]);

const paceOptions = computed(() => [
  { label: t("home.optionLabels.relaxed"), value: "轻松" },
  { label: t("home.optionLabels.moderate"), value: "适中" },
  { label: t("home.optionLabels.packed"), value: "紧凑" },
]);

const hotelLevelOptions = computed(() => [
  { label: t("home.optionLabels.comfort"), value: "舒适型" },
  { label: t("home.optionLabels.upscale"), value: "高档型" },
  { label: t("home.optionLabels.economy"), value: "经济型" },
]);

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const today = new Date();
today.setHours(0, 0, 0, 0);
const todayPlus2 = new Date(today);
todayPlus2.setDate(todayPlus2.getDate() + 2);

const formState = reactive({
  origin: "北京",
  destinations: ["大理"],
  startDate: formatDate(today),
  endDate: formatDate(todayPlus2),
  travelers: 2,
  budget: 3200,
  hotelLevel: "舒适型",
  pace: "轻松",
  preferences: ["自然风景", "拍照", "美食"],
  dietaryPreferences: ["少辣"],
  notes: "不想太早起床，希望安排一个适合看日落的地点。",
  deepPlanningReflectionRounds: 2,
  deepPlanningSearchEngine: "tavily" as "tavily" | "searxng",
});

const submittingMode = ref<"quick" | "deep" | null>(null);
const pendingMode = ref<"quick" | "deep" | null>(null);
const confirmOpen = ref(false);
const confirmChecking = ref(false);
const spanCheck = ref<DestinationSpanCheckResponse | null>(null);
const spanCheckError = ref("");
const locationOptions = ref<LocationSuggestion[]>([
  { label: "北京", value: "北京" },
  { label: "大理", value: "大理" },
]);
const locationSearching = ref(false);
let locationSearchTimer: ReturnType<typeof setTimeout> | undefined;
let locationSearchSeq = 0;

const destinationText = computed(() => formState.destinations.join("、"));
const selectedDestinations = computed(() => formState.destinations.map((item) => item.trim()).filter(Boolean));
const confirmationRows = computed(() => [
  { label: t("home.fields.origin"), value: formState.origin || t("common.pending") },
  { label: t("home.fields.destination"), value: destinationText.value || t("common.pending") },
  { label: t("home.fields.dateRange"), value: `${formState.startDate} 至 ${formState.endDate}` },
  { label: t("home.fields.dayCount"), value: t("home.duration", { count: dayCount.value }) },
  { label: t("home.fields.travelers"), value: String(formState.travelers) },
  { label: t("home.fields.budget"), value: `¥${formState.budget}` },
  { label: t("home.fields.pace"), value: formState.pace },
  { label: t("home.fields.hotelLevel"), value: formState.hotelLevel },
  { label: t("home.fields.preferences"), value: formState.preferences.join("、") || "无" },
  { label: t("home.fields.dietary"), value: formState.dietaryPreferences.join("、") || "无" },
]);

function mergeLocationOptions(items: LocationSuggestion[]) {
  const selectedOptions = [formState.origin, ...formState.destinations]
    .filter(Boolean)
    .map((value) => ({ label: value, value }));
  const seen = new Set<string>();
  locationOptions.value = [...selectedOptions, ...items].filter((item) => {
    if (!item.value || seen.has(item.value)) {
      return false;
    }
    seen.add(item.value);
    return true;
  });
}

function handleLocationSearch(keyword: string) {
  const query = keyword.trim();
  if (locationSearchTimer) {
    clearTimeout(locationSearchTimer);
  }
  if (!query) {
    mergeLocationOptions([]);
    locationSearching.value = false;
    return;
  }

  const seq = ++locationSearchSeq;
  locationSearching.value = true;
  locationSearchTimer = setTimeout(async () => {
    try {
      const response = await fetchLocationSuggestions(query, 12);
      if (seq === locationSearchSeq) {
        mergeLocationOptions(response.items);
      }
    } catch (error) {
      console.warn("location suggestions failed", error);
      if (seq === locationSearchSeq) {
        mergeLocationOptions([{ label: query, value: query }]);
      }
    } finally {
      if (seq === locationSearchSeq) {
        locationSearching.value = false;
      }
    }
  }, 240);
}

const dateRange = computed<[string, string]>({
  get: () => [formState.startDate, formState.endDate] as [string, string],
  set: (value: [string, string]) => {
    const [start, end] = value;
    formState.startDate = start;
    formState.endDate = end;
  },
});

const dayCount = computed(() => {
  const start = new Date(formState.startDate);
  const end = new Date(formState.endDate);
  const diff = end.getTime() - start.getTime();
  return Number.isNaN(diff) ? 0 : Math.max(Math.floor(diff / 86400000) + 1, 0);
});

function disabledPastDate(current: { valueOf: () => number } | Date | string): boolean {
  const time =
    typeof current === "string"
      ? new Date(current).getTime()
      : current instanceof Date
        ? current.getTime()
        : current.valueOf();
  return time < today.getTime();
}

function buildPayload(): TripRequestPayload {
  return {
    origin: formState.origin,
    destination: destinationText.value,
    start_date: formState.startDate,
    end_date: formState.endDate,
    travelers: formState.travelers,
    budget: formState.budget,
    preferences: formState.preferences,
    pace: formState.pace,
    dietary_preferences: formState.dietaryPreferences,
    hotel_level: formState.hotelLevel,
    special_notes: formState.notes,
    deep_planning_reflection_rounds: formState.deepPlanningReflectionRounds,
    deep_planning_search_engine: formState.deepPlanningSearchEngine,
  };
}

async function openSubmitConfirmation(mode: "quick" | "deep") {
  if (!formState.origin.trim()) {
    message.warning("请先填写出发地。");
    return;
  }
  if (!selectedDestinations.value.length) {
    message.warning("请至少填写一个目的地。");
    return;
  }
  if (dayCount.value <= 0) {
    message.warning("请选择有效的出行日期。");
    return;
  }

  pendingMode.value = mode;
  confirmOpen.value = true;
  spanCheck.value = null;
  spanCheckError.value = "";

  if (selectedDestinations.value.length < 2) {
    return;
  }

  confirmChecking.value = true;
  try {
    spanCheck.value = await checkDestinationSpan(selectedDestinations.value);
  } catch (error) {
    console.warn("destination span check failed", error);
    spanCheckError.value = "暂时无法完成目的地跨度校验，你仍可以确认继续。";
  } finally {
    confirmChecking.value = false;
  }
}

function closeSubmitConfirmation() {
  if (submittingMode.value !== null) {
    return;
  }
  confirmOpen.value = false;
  pendingMode.value = null;
}

function showGenerationError(error: unknown, label: string) {
  console.error(error);
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") {
      message.error(t("home.messages.timeout", { label }));
    } else if (error.response) {
      message.error(t("home.messages.responseError", { label, status: error.response.status }));
    } else {
      message.error(t("home.messages.connectionError", { label }));
    }
  } else {
    message.error(t("home.messages.genericError", { label }));
  }
}

async function handleQuickSubmit() {
  submittingMode.value = "quick";
  try {
    const itinerary = await generateTrip(buildPayload());
    message.success(t("home.messages.quickSuccess"));
    emit("generated", itinerary);
  } catch (error) {
    showGenerationError(error, t("home.messages.quickLabel"));
  } finally {
    submittingMode.value = null;
  }
}

async function handleDeepSubmit() {
  submittingMode.value = "deep";
  try {
    const item = await generateDeepTrip(buildPayload());
    message.success(t("home.messages.deepSuccess"));
    emit("deepSubmitted", item);
  } catch (error) {
    showGenerationError(error, t("home.messages.deepLabel"));
  } finally {
    submittingMode.value = null;
  }
}

async function confirmSubmit() {
  if (pendingMode.value === "quick") {
    await handleQuickSubmit();
  } else if (pendingMode.value === "deep") {
    await handleDeepSubmit();
  }
  confirmOpen.value = false;
  pendingMode.value = null;
}
</script>

<template>
  <section class="home-page">
    <section class="planner-section" aria-labelledby="planner-title">
      <div class="planner-hero">
        <div>
          <span class="section-heading__kicker">VoyageOS Planner</span>
          <h2 id="planner-title">{{ t("home.title") }}</h2>
          <p>{{ t("home.description") }}</p>
        </div>
        <div class="planner-hero__summary" :aria-label="t('home.summaryLabel')">
          <div>
            <span>Destination</span>
            <strong>{{ destinationText }}</strong>
          </div>
          <div>
            <span>Duration</span>
            <strong>{{ t("home.duration", { count: dayCount }) }}</strong>
          </div>
          <div>
            <span>Budget</span>
            <strong>¥{{ formState.budget }}</strong>
          </div>
        </div>
      </div>

      <div class="planner-grid">
        <div class="planner-card planner-card--primary">
        <div class="section-title">
          <span class="section-title__icon">{{ t("home.sections.destinationIcon") }}</span>
          <span>{{ t("home.sections.destination") }}</span>
        </div>

        <div class="destination-fields">
          <div class="destination-fields__place">
            <label class="field-label">{{ t("home.fields.origin") }}</label>
            <a-select
              v-model:value="formState.origin"
              show-search
              class="destination-fields__control"
              :filter-option="false"
              :loading="locationSearching"
              :options="locationOptions"
              :placeholder="t('home.fields.originPlaceholder')"
              @search="handleLocationSearch"
            />
          </div>
          <div class="destination-fields__place destination-fields__destination">
            <label class="field-label">{{ t("home.fields.destination") }}</label>
            <a-select
              v-model:value="formState.destinations"
              mode="tags"
              show-search
              class="destination-fields__control"
              :filter-option="false"
              :loading="locationSearching"
              :options="locationOptions"
              :placeholder="t('home.fields.destinationPlaceholder')"
              @search="handleLocationSearch"
            />
          </div>
          <div class="destination-fields__compact">
            <label class="field-label">{{ t("home.fields.travelers") }}</label>
            <a-input-number v-model:value="formState.travelers" :min="1" style="width: 100%" />
          </div>
          <div class="destination-fields__compact">
            <label class="field-label">{{ t("home.fields.dayCount") }}</label>
            <div class="pill-box">{{ t("home.duration", { count: dayCount }) }}</div>
          </div>
          <div class="destination-fields__dates">
            <label class="field-label">{{ t("home.fields.dateRange") }}</label>
            <a-range-picker
              v-model:value="dateRange"
              :allow-clear="false"
              :disabled-date="disabledPastDate"
              value-format="YYYY-MM-DD"
              format="YYYY-MM-DD"
              style="width: 100%"
              :placeholder="[t('home.fields.startDate'), t('home.fields.endDate')]"
            />
          </div>
        </div>
      </div>

        <div class="planner-card">
        <div class="section-title">
          <span class="section-title__icon">{{ t("home.sections.preferenceIcon") }}</span>
          <span>{{ t("home.sections.preference") }}</span>
        </div>

        <a-row :gutter="[16, 16]">
          <a-col :xs="24" :md="8">
            <label class="field-label">{{ t("home.fields.pace") }}</label>
            <a-select
              v-model:value="formState.pace"
              :options="paceOptions"
            />
          </a-col>
          <a-col :xs="24" :md="8">
            <label class="field-label">{{ t("home.fields.hotelLevel") }}</label>
            <a-select
              v-model:value="formState.hotelLevel"
              :options="hotelLevelOptions"
            />
          </a-col>
          <a-col :xs="24" :md="8">
            <label class="field-label">{{ t("home.fields.budget") }}</label>
            <a-input-number v-model:value="formState.budget" :min="0" style="width: 100%" />
          </a-col>
        </a-row>

        <div class="checkbox-area">
          <label class="field-label">{{ t("home.fields.preferences") }}</label>
          <a-checkbox-group v-model:value="formState.preferences" :options="preferenceOptions" />
        </div>

        <div class="checkbox-area">
          <label class="field-label">{{ t("home.fields.dietary") }}</label>
          <a-checkbox-group
            v-model:value="formState.dietaryPreferences"
            :options="dietaryOptions"
          />
        </div>
      </div>
      </div>

      <div class="planner-card">
        <div class="section-title">
          <span class="section-title__icon">{{ t("home.sections.notesIcon") }}</span>
          <span>{{ t("home.sections.notes") }}</span>
        </div>
        <a-textarea
          v-model:value="formState.notes"
          :rows="4"
          :placeholder="t('home.fields.notesPlaceholder')"
        />
      </div>

      <div class="planner-card">
        <div class="section-title">
          <span class="section-title__icon">{{ t("home.sections.researchIcon") }}</span>
          <span>{{ t("home.sections.research") }}</span>
        </div>

        <a-row :gutter="[16, 16]">
          <a-col :xs="24" :md="8">
            <label class="field-label">{{ t("home.fields.reflectionRounds") }}</label>
            <a-input-number
              v-model:value="formState.deepPlanningReflectionRounds"
              :min="0"
              :max="5"
              style="width: 100%"
            />
          </a-col>
          <a-col :xs="24" :md="16">
            <label class="field-label">{{ t("home.fields.searchEngine") }}</label>
            <a-segmented
              v-model:value="formState.deepPlanningSearchEngine"
              block
              :options="[
                { label: 'Tavily', value: 'tavily' },
                { label: 'SearXNG', value: 'searxng' }
              ]"
            />
          </a-col>
        </a-row>
      </div>

      <div class="submit-panel">
        <div class="submit-panel__copy">
          <span>Launch</span>
          <strong>{{ t("home.submit.label") }}</strong>
          <p>{{ t("home.submit.description") }}</p>
        </div>
        <div class="submit-panel__actions">
          <button
            class="submit-panel__button submit-panel__button--quick"
            :disabled="submittingMode !== null"
            @click="openSubmitConfirmation('quick')"
          >
            {{ submittingMode === "quick" ? t("home.submit.quickLoading") : t("home.submit.quick") }}
          </button>
          <button
            class="submit-panel__button submit-panel__button--deep"
            :disabled="submittingMode !== null"
            @click="openSubmitConfirmation('deep')"
          >
            {{ submittingMode === "deep" ? t("home.submit.deepLoading") : t("home.submit.deep") }}
          </button>
        </div>
      </div>

      <a-modal
        :open="confirmOpen"
        :title="pendingMode === 'deep' ? '确认深度规划信息' : '确认快速规划信息'"
        :confirm-loading="submittingMode !== null"
        width="680px"
        ok-text="确认继续"
        cancel-text="取消"
        @ok="confirmSubmit"
        @cancel="closeSubmitConfirmation"
      >
        <div class="submit-confirmation">
          <div v-if="confirmChecking" class="submit-confirmation__notice">
            正在校验多个目的地之间的距离跨度...
          </div>
          <div
            v-else-if="spanCheck?.is_large_span"
            class="submit-confirmation__notice submit-confirmation__notice--warning"
          >
            <strong>目的地跨度较大</strong>
            <span>
              {{ spanCheck.max_pair.join(" 与 ") }} 相距约 {{ spanCheck.max_distance_km }} km，
              可能更适合拆成多段旅行或增加交通缓冲。确认后仍会继续生成。
            </span>
          </div>
          <div v-else-if="spanCheck && selectedDestinations.length > 1" class="submit-confirmation__notice">
            已完成跨度校验，当前多个目的地最大距离约 {{ spanCheck.max_distance_km }} km。
          </div>
          <div v-else-if="spanCheckError" class="submit-confirmation__notice submit-confirmation__notice--warning">
            {{ spanCheckError }}
          </div>

          <div class="submit-confirmation__grid">
            <div
              v-for="row in confirmationRows"
              :key="row.label"
              class="submit-confirmation__item"
            >
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>

          <div v-if="formState.notes" class="submit-confirmation__notes">
            <span>{{ t("home.sections.notes") }}</span>
            <p>{{ formState.notes }}</p>
          </div>
        </div>
      </a-modal>
    </section>
  </section>
</template>

<style scoped>
.home-page {
  display: grid;
  gap: 24px;
}

.section-heading__kicker {
  color: #9a6b23;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.planner-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.8fr);
  gap: 22px;
  align-items: end;
  padding: 34px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 28px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(240, 246, 242, 0.82)),
    radial-gradient(circle at 92% 12%, rgba(215, 173, 88, 0.18), transparent 30%);
  box-shadow: 0 26px 70px rgba(34, 61, 57, 0.1);
}

.planner-hero h2 {
  margin: 10px 0 0;
  color: #173936;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 44px;
  line-height: 1.14;
}

.planner-hero p {
  max-width: 720px;
  margin: 12px 0 0;
  color: #63726e;
  font-size: 16px;
  line-height: 1.7;
}

.planner-hero__summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.planner-hero__summary div {
  min-height: 96px;
  padding: 16px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
}

.planner-hero__summary span,
.planner-hero__summary strong {
  display: block;
}

.planner-hero__summary span {
  color: #9a6b23;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.planner-hero__summary strong {
  margin-top: 12px;
  color: #143c38;
  font-size: 24px;
  line-height: 1.1;
}

.planner-section {
  display: grid;
  gap: 20px;
}

.planner-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
  gap: 20px;
}

.planner-card {
  position: relative;
  overflow: hidden;
  padding: 26px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(250, 251, 247, 0.82));
  box-shadow: 0 22px 55px rgba(34, 61, 57, 0.08);
  backdrop-filter: blur(14px);
}

.planner-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, #173936, #d7ad58);
  opacity: 0.85;
}

.planner-card--primary {
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.92), rgba(238, 246, 241, 0.82)),
    radial-gradient(circle at 90% 8%, rgba(215, 173, 88, 0.14), transparent 28%);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(25, 66, 63, 0.12);
  color: #173936;
  font-size: 16px;
  font-weight: 700;
}

.section-title__icon {
  border-radius: 999px;
  padding: 4px 9px;
  background: rgba(215, 173, 88, 0.16);
  color: #8f661f;
  font-size: 12px;
  font-weight: 900;
}

.field-label {
  display: block;
  margin-bottom: 9px;
  color: #52645f;
  font-size: 13px;
  font-weight: 800;
}

.destination-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: end;
}

.destination-fields__dates {
  grid-column: 1 / -1;
  max-width: none;
}

.destination-fields__place {
  grid-column: 1 / -1;
}

.destination-fields__compact,
.destination-fields__place {
  min-width: 0;
}

.destination-fields__control {
  width: 100%;
}

.destination-fields__destination :deep(.ant-select-selector) {
  min-height: 34px;
  height: auto !important;
  padding-top: 2px !important;
  padding-bottom: 2px !important;
}

.destination-fields__destination :deep(.ant-select-selection-overflow) {
  min-height: 28px;
}

.destination-fields__destination :deep(.ant-select-selection-item) {
  border-radius: 999px;
  background: rgba(20, 60, 56, 0.1);
  color: #173936;
  font-weight: 700;
}

.pill-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, #143c38, #1f574f);
  color: #ffffff;
  font-weight: 700;
}

.checkbox-area {
  margin-top: 18px;
}

.submit-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 20px;
  align-items: center;
  padding: 24px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 26px;
  background:
    linear-gradient(135deg, rgba(20, 60, 56, 0.96), rgba(13, 39, 37, 0.96)),
    radial-gradient(circle at 90% 0%, rgba(215, 173, 88, 0.26), transparent 30%);
  color: #ffffff;
  box-shadow: 0 24px 64px rgba(20, 60, 56, 0.18);
}

.submit-panel__copy span,
.submit-panel__copy strong,
.submit-panel__copy p {
  display: block;
}

.submit-panel__copy span {
  color: #d7ad58;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.submit-panel__copy strong {
  margin-top: 8px;
  font-size: 24px;
}

.submit-panel__copy p {
  max-width: 680px;
  margin: 8px 0 0;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.7;
}

.submit-panel__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 14px;
}

.submit-panel__button {
  min-width: 220px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 999px;
  padding: 14px 28px;
  background: #ffffff;
  color: #143c38;
  font-size: 15px;
  font-weight: 900;
  cursor: pointer;
  box-shadow: 0 18px 35px rgba(0, 0, 0, 0.16);
}

.submit-panel__button--quick {
  background: #ffffff;
  color: #143c38;
}

.submit-panel__button--deep {
  background: #d7ad58;
  color: #241b0c;
}

.submit-panel__button:disabled {
  opacity: 0.7;
  cursor: wait;
}

.submit-confirmation {
  display: grid;
  gap: 16px;
}

.submit-confirmation__notice {
  display: grid;
  gap: 5px;
  border: 1px solid rgba(25, 66, 63, 0.12);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(238, 246, 241, 0.9);
  color: #173936;
  line-height: 1.6;
}

.submit-confirmation__notice--warning {
  border-color: rgba(215, 173, 88, 0.42);
  background: rgba(215, 173, 88, 0.12);
}

.submit-confirmation__notice strong {
  color: #8f661f;
}

.submit-confirmation__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.submit-confirmation__item {
  min-width: 0;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.78);
}

.submit-confirmation__item span,
.submit-confirmation__notes span {
  display: block;
  color: #8f661f;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.submit-confirmation__item strong {
  display: block;
  margin-top: 7px;
  color: #143c38;
  font-size: 15px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.submit-confirmation__notes {
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 14px;
  padding: 12px;
  background: rgba(250, 251, 247, 0.92);
}

.submit-confirmation__notes p {
  margin: 7px 0 0;
  color: #173936;
  line-height: 1.7;
}

:deep(.ant-input),
:deep(.ant-input-number),
:deep(.ant-select-selector),
:deep(.ant-input-number-input),
:deep(.ant-input-affix-wrapper),
:deep(.ant-picker),
:deep(textarea.ant-input) {
  border-color: rgba(25, 66, 63, 0.16) !important;
  border-radius: 12px !important;
  background: rgba(255, 255, 255, 0.78) !important;
  color: #173936 !important;
}

:deep(.ant-input),
:deep(.ant-input-number),
:deep(.ant-select-selector),
:deep(.ant-input-affix-wrapper) {
  min-height: 34px;
}

:deep(.ant-picker) {
  min-height: 34px;
}

:deep(.ant-picker-input > input) {
  color: #173936 !important;
  font-weight: 500;
}

:deep(.ant-input:hover),
:deep(.ant-input-number:hover),
:deep(.ant-select-selector:hover),
:deep(.ant-input-affix-wrapper:hover),
:deep(.ant-picker:hover),
:deep(textarea.ant-input:hover) {
  border-color: rgba(154, 107, 35, 0.42) !important;
}

:deep(.ant-input:focus),
:deep(.ant-input-focused),
:deep(.ant-input-number-focused),
:deep(.ant-select-focused .ant-select-selector),
:deep(.ant-input-affix-wrapper-focused),
:deep(.ant-picker-focused),
:deep(textarea.ant-input:focus) {
  border-color: #9a6b23 !important;
  box-shadow: 0 0 0 3px rgba(215, 173, 88, 0.16) !important;
}

:deep(.ant-checkbox-wrapper) {
  color: #314844;
  font-weight: 600;
}

:deep(.ant-checkbox-checked .ant-checkbox-inner) {
  border-color: #143c38;
  background-color: #143c38;
}

:deep(.ant-checkbox-wrapper:hover .ant-checkbox-inner),
:deep(.ant-checkbox:hover .ant-checkbox-inner) {
  border-color: #9a6b23;
}

:deep(.ant-select-arrow),
:deep(.ant-input-number-handler-wrap) {
  color: #52645f;
}

:deep(.ant-segmented) {
  padding: 4px;
  border: 1px solid rgba(25, 66, 63, 0.12);
  border-radius: 14px;
  background: rgba(238, 242, 235, 0.9);
}

:deep(.ant-segmented-item) {
  border-radius: 10px;
  color: #52645f;
  font-weight: 800;
}

:deep(.ant-segmented-item-selected) {
  background: #143c38 !important;
  color: #ffffff;
  box-shadow: 0 8px 18px rgba(20, 60, 56, 0.12);
}

:deep(.ant-modal-content) {
  border: 1px solid rgba(25, 66, 63, 0.12);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(250, 251, 247, 0.96)) !important;
  box-shadow: 0 28px 76px rgba(20, 60, 56, 0.18);
}

:deep(.ant-modal-title) {
  color: #143c38 !important;
  font-weight: 900 !important;
}

:deep(.ant-modal-footer .ant-btn-primary) {
  background: #143c38;
  border-color: #143c38;
}

:deep(.ant-modal-footer .ant-btn-primary:hover) {
  background: #1f574f !important;
  border-color: #1f574f !important;
}

@media (max-width: 640px) {
  .planner-hero,
  .planner-grid,
  .submit-panel {
    grid-template-columns: 1fr;
  }

  .planner-hero {
    padding: 24px 18px;
  }

  .planner-hero h2 {
    font-size: 30px;
  }

  .planner-hero__summary {
    grid-template-columns: 1fr;
  }

  .submit-panel__button {
    width: 100%;
  }

  .destination-fields {
    grid-template-columns: 1fr;
  }

  .destination-fields__dates {
    max-width: none;
  }

  .submit-confirmation__grid {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 641px) and (max-width: 1080px) {
  .planner-hero,
  .planner-grid,
  .submit-panel {
    grid-template-columns: 1fr;
  }

  .destination-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .destination-fields__dates {
    max-width: none;
  }
}
</style>
