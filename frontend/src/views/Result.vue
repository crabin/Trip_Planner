<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { message } from "ant-design-vue";

import AmapTripMap from "../components/AmapTripMap.vue";
import {
  editTrip,
  exportTripMarkdown,
  exportTripPdf,
  fetchWeatherForecast,
  saveTrip,
} from "../services/api";
import type { HotelItem, Itinerary, MealItem, SpotItem, WeatherForecastResponse } from "../types";

const props = defineProps<{
  itinerary: Itinerary | null;
}>();

const emit = defineEmits<{
  backHome: [];
  viewHistory: [];
  updated: [itinerary: Itinerary];
}>();

const saving = ref(false);
const exportingPdf = ref(false);
const exportingMarkdown = ref(false);
const editing = ref(false);
const editScope = ref("day_1");
const editInstruction = ref("这一天节奏更轻松一点，减少固定安排。");
const weatherLoading = ref(false);
const weatherError = ref("");
const weather = ref<WeatherForecastResponse | null>(null);
const mapExpanded = ref(false);

function formatShortDate(dateText?: string | null): string {
  if (!dateText) {
    return "待定";
  }

  const parts = dateText.split("-");
  if (parts.length !== 3) {
    return dateText;
  }

  return `${parts[1]}-${parts[2]}`;
}

function formatWeatherDate(dateText?: string | null, week?: string | null): string {
  const weekdayMap: Record<string, string> = {
    "1": "周一",
    "2": "周二",
    "3": "周三",
    "4": "周四",
    "5": "周五",
    "6": "周六",
    "7": "周日",
  };
  const weekday = week ? weekdayMap[week] || `周${week}` : "";
  return [formatShortDate(dateText), weekday].filter(Boolean).join(" ");
}

function formatMapRating(value?: number | null): string {
  return value != null ? `${value.toFixed(1)} 分` : "暂无评分";
}

function formatReferenceCost(value?: number | null, fallback?: number | null): string {
  if (value != null) {
    return `¥${value.toFixed(0)} 参考`;
  }
  if (fallback != null && fallback > 0) {
    return `¥${fallback.toFixed(0)} 预算`;
  }
  if (fallback === 0) {
    return "¥0 预算";
  }
  return "价格待查询";
}

function formatDistance(value?: number | null): string {
  if (value == null) {
    return "";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)} km`;
  }
  return `${value.toFixed(0)} m`;
}

function buildTagText(tags?: string[]): string {
  const visibleTags = (tags || []).filter(Boolean).slice(0, 3);
  return visibleTags.join(" · ");
}

function hasPoiInfo(item?: MealItem | HotelItem | SpotItem | null): boolean {
  if (!item) {
    return false;
  }
  return Boolean(
    item.poi_id ||
      item.map_rating != null ||
      item.map_average_cost != null ||
      item.map_tags?.length ||
      item.map_business_area ||
      item.map_open_time_today ||
      item.map_type ||
      item.address ||
      item.image_url
  );
}

function buildRecommendationReason(item: MealItem | HotelItem, kind: "meal" | "hotel"): string {
  if (item.recommendation_reason) {
    return item.recommendation_reason;
  }
  const reasons: string[] = [];
  if (item.ranking_label) {
    reasons.push(item.ranking_label);
  }
  if (item.map_rating != null) {
    reasons.push(`高德评分 ${item.map_rating.toFixed(1)}`);
  }
  if (item.review_count != null) {
    reasons.push(`${item.review_count} 条评价`);
  }
  const distance = formatDistance(item.map_distance_meters);
  if (distance) {
    reasons.push(`距离当日景点约 ${distance}`);
  }
  if (item.map_tags?.length) {
    reasons.push(buildTagText(item.map_tags));
  }
  if (item.map_business_area) {
    reasons.push(`位于${item.map_business_area}商圈`);
  }
  if (item.map_open_time_today) {
    reasons.push(`今日营业 ${item.map_open_time_today}`);
  }
  if (!reasons.length && item.address) {
    reasons.push("已匹配真实地图地址");
  }
  if (!reasons.length) {
    reasons.push(kind === "meal" ? "匹配当日餐饮预算与地点" : "匹配当日住宿预算与地点");
  }
  return reasons.join("，");
}

function buildContactText(item: MealItem | HotelItem | SpotItem): string {
  return [item.map_tel, item.address].filter(Boolean).join(" · ");
}

function buildMapDetailText(item: MealItem | HotelItem | SpotItem): string {
  return [
    item.map_business_area ? `${item.map_business_area}商圈` : "",
    item.map_open_time_today ? `今日 ${item.map_open_time_today}` : "",
    item.map_type ? item.map_type.split(";").slice(-1)[0] : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function buildSourceText(item: MealItem | HotelItem): string {
  const sourceMap: Record<string, string> = {
    amap: "高德",
    meituan: "美团",
    dianping: "大众点评",
  };
  return item.data_source ? sourceMap[item.data_source] || item.data_source : "";
}

const budgetItems = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  const budget = props.itinerary.budget_breakdown;
  return [
    { label: "景点门票", value: `¥${budget.tickets.toFixed(0)}` },
    { label: "酒店住宿", value: `¥${budget.hotel.toFixed(0)}` },
    { label: "餐饮费用", value: `¥${budget.meals.toFixed(0)}` },
    { label: "交通费用", value: `¥${budget.transport.toFixed(0)}` },
    { label: "其他费用", value: `¥${budget.other.toFixed(0)}` },
  ];
});

const dayBudgetItems = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days.map((day) => {
    const tickets = day.spots.reduce((sum, spot) => sum + (spot.estimated_cost ?? 0), 0);
    const meals = day.meals.reduce((sum, meal) => sum + (meal.estimated_cost ?? 0), 0);
    const transport = day.transport.reduce((sum, item) => sum + (item.estimated_cost ?? 0), 0);
    const hotel = day.hotel?.estimated_cost ?? 0;
    const total = tickets + meals + transport + hotel;

    return {
      key: day.day_index,
      title: `第${day.day_index}天`,
      subtitle: day.theme || "未命名主题",
      tickets,
      meals,
      transport,
      hotel,
      total,
    };
  });
});

const mapPoints = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days.flatMap((day) => {
    const spotPoints = day.spots.map((spot) => ({
      key: `spot-${day.day_index}-${spot.name}`,
      kind: "spot" as const,
      label: "景点",
      dayIndex: day.day_index,
      date: day.date || "待定",
      theme: day.theme || "未命名主题",
      name: spot.name,
      address: spot.address || spot.location || "待补充",
      latitude: spot.latitude,
      longitude: spot.longitude,
      poiId: spot.poi_id,
      imageUrl: spot.image_url,
      description: spot.description || "暂无说明",
      rating: spot.map_rating,
      averageCost: spot.map_average_cost,
      estimatedCost: spot.estimated_cost,
      tags: spot.map_tags || [],
      distanceMeters: spot.map_distance_meters,
      tel: spot.map_tel,
      businessArea: spot.map_business_area,
      openTimeToday: spot.map_open_time_today,
      type: spot.map_type,
      recommended: false,
    }));

    const hotelCandidates = day.hotel_candidates || [];
    const hotelsForMap = hotelCandidates.length ? hotelCandidates : day.hotel ? [day.hotel] : [];
    const hotelPoints = hotelsForMap.map((hotel, index) => ({
      key: `hotel-${day.day_index}-${index}-${hotel.name}`,
      kind: "hotel" as const,
      label: hotel.is_recommended === false ? "候选酒店" : "推荐酒店",
      dayIndex: day.day_index,
      date: day.date || "待定",
      theme: day.theme || "未命名主题",
      name: hotel.name,
      address: hotel.address || hotel.location || "待补充",
      latitude: hotel.latitude,
      longitude: hotel.longitude,
      poiId: hotel.poi_id,
      imageUrl: hotel.image_url,
      description: hotel.recommendation_reason || (hotel.level ? `${hotel.level}住宿` : "住宿候选"),
      rating: hotel.map_rating,
      averageCost: hotel.map_average_cost,
      estimatedCost: hotel.estimated_cost,
      tags: hotel.map_tags || [],
      distanceMeters: hotel.map_distance_meters,
      tel: hotel.map_tel,
      businessArea: hotel.map_business_area,
      openTimeToday: hotel.map_open_time_today,
      type: hotel.map_type,
      recommended: hotel.is_recommended !== false,
    }));

    const mealCandidates = day.meal_candidates || [];
    const mealsForMap = mealCandidates.length ? mealCandidates : day.meals;
    const mealPoints = mealsForMap.map((meal, index) => ({
      key: `meal-${day.day_index}-${index}-${meal.meal_type}-${meal.name}`,
      kind: "meal" as const,
      label: `${meal.is_recommended === false ? "候选" : "推荐"}${meal.meal_type || "餐饮"}`,
      dayIndex: day.day_index,
      date: day.date || "待定",
      theme: day.theme || "未命名主题",
      name: meal.name,
      address: meal.address || "待补充",
      latitude: meal.latitude,
      longitude: meal.longitude,
      poiId: meal.poi_id,
      imageUrl: meal.image_url,
      description: meal.notes || "当日推荐餐饮",
      rating: meal.map_rating,
      averageCost: meal.map_average_cost,
      estimatedCost: meal.estimated_cost,
      tags: meal.map_tags || [],
      distanceMeters: meal.map_distance_meters,
      tel: meal.map_tel,
      businessArea: meal.map_business_area,
      openTimeToday: meal.map_open_time_today,
      type: meal.map_type,
      recommended: meal.is_recommended !== false,
    }));

    return [...spotPoints, ...hotelPoints, ...mealPoints];
  });
});

const scenicMapPoints = computed(() =>
  mapPoints.value.filter((point) => point.kind === "spot")
);

const hotelRecommendationDays = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days
    .map((day) => ({
      ...day,
      hasRecommendedHotel: hasPoiInfo(day.hotel),
    }))
    .filter((day) => day.hotel);
});

const mealRecommendationDays = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  return props.itinerary.days
    .map((day) => ({
      ...day,
      visibleMeals: day.meals.filter((meal) => (meal.is_recommended ?? true) && (hasPoiInfo(meal) || meal.name)),
    }))
    .filter((day) => day.visibleMeals.length);
});

const technicalTipKeywords = [
  "LLM",
  "RAG",
  "LangChain",
  "Chroma",
  "演示",
  "测试",
  "规则",
  "模型",
  "源码",
];

const rainWeatherKeywords = ["雨", "阵雨", "雷阵雨", "小雨", "中雨", "大雨"];
const sunnyTipKeywords = ["防晒", "太阳", "日照", "晒"];

const weatherText = computed(() => {
  if (!weather.value) {
    return "";
  }

  return weather.value.days
    .map((day) => `${day.day_weather || ""}${day.night_weather || ""}`)
    .join(" ");
});

const hasRainyWeather = computed(() => {
  return rainWeatherKeywords.some((keyword) => weatherText.value.includes(keyword));
});

const displayTips = computed(() => {
  if (!props.itinerary) {
    return [];
  }

  const tips = props.itinerary.tips
    .map((tip) => tip.trim())
    .filter(Boolean)
    .filter((tip) => !technicalTipKeywords.some((keyword) => tip.includes(keyword)));

  const weatherAwareTips = hasRainyWeather.value
    ? tips.filter((tip) => !sunnyTipKeywords.some((keyword) => tip.includes(keyword)))
    : tips;

  if (hasRainyWeather.value) {
    weatherAwareTips.push("天气可能有雨，建议随身带伞或轻便雨衣。");
    weatherAwareTips.push("阴雨天路面湿滑，洱海边和古镇石板路建议穿防滑鞋。");
  }

  const uniqueTips = Array.from(new Set(weatherAwareTips));
  if (uniqueTips.length) {
    return uniqueTips;
  }

  return [
    `建议根据${props.itinerary.destination}当天实时天气准备雨具或薄外套。`,
    "古镇、生态廊道和石板路更适合慢慢走，鞋子尽量选择舒适防滑的款式。",
  ];
});

function buildVisibleItinerary(): Itinerary | null {
  if (!props.itinerary) {
    return null;
  }

  return {
    ...props.itinerary,
    tips: displayTips.value,
  };
}

function openExportBlob(exportWindow: Window | null, blob: Blob) {
  const exportUrl = URL.createObjectURL(blob);
  if (exportWindow) {
    exportWindow.location.href = exportUrl;
  } else {
    window.location.href = exportUrl;
  }
  window.setTimeout(() => URL.revokeObjectURL(exportUrl), 60_000);
}

async function loadWeather() {
  if (!props.itinerary?.destination) {
    weather.value = null;
    return;
  }

  weatherLoading.value = true;
  weatherError.value = "";
  try {
    weather.value = await fetchWeatherForecast(props.itinerary.destination);
  } catch (error) {
    console.error(error);
    weather.value = null;
    weatherError.value = "天气信息加载失败。";
  } finally {
    weatherLoading.value = false;
  }
}

watch(
  () => props.itinerary?.destination,
  () => {
    void loadWeather();
  },
  { immediate: true }
);

watch(
  () => props.itinerary?.trip_id,
  () => {
    const firstDay = props.itinerary?.days[0];
    editScope.value = firstDay ? `day_${firstDay.day_index}` : "day_1";
  },
  { immediate: true }
);

async function openPdfExport() {
  const itineraryToExport = buildVisibleItinerary();
  if (!itineraryToExport) {
    return;
  }

  const exportWindow = window.open("about:blank", "_blank");
  exportingPdf.value = true;
  try {
    const pdfBlob = await exportTripPdf(itineraryToExport);
    openExportBlob(exportWindow, pdfBlob);
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("生成 PDF 失败。");
  } finally {
    exportingPdf.value = false;
  }
}

async function openMarkdownExport() {
  const itineraryToExport = buildVisibleItinerary();
  if (!itineraryToExport) {
    return;
  }

  const exportWindow = window.open("about:blank", "_blank");
  exportingMarkdown.value = true;
  try {
    const markdownBlob = await exportTripMarkdown(itineraryToExport);
    openExportBlob(exportWindow, markdownBlob);
  } catch (error) {
    console.error(error);
    exportWindow?.close();
    message.error("生成 Markdown 失败。");
  } finally {
    exportingMarkdown.value = false;
  }
}

async function handleSave() {
  const itineraryToSave = buildVisibleItinerary();
  if (!itineraryToSave) {
    return;
  }

  saving.value = true;
  try {
    await saveTrip(itineraryToSave);
    message.success("行程已保存，可以去历史列表查看。");
  } catch (error) {
    console.error(error);
    message.error("保存行程失败。");
  } finally {
    saving.value = false;
  }
}

async function handleEdit() {
  if (!props.itinerary) {
    return;
  }

  const instruction = editInstruction.value.trim();
  if (!instruction) {
    message.warning("请先输入想如何调整行程。");
    return;
  }

  editing.value = true;
  try {
    const updatedItinerary = await editTrip({
      trip_id: props.itinerary.trip_id,
      current_itinerary: props.itinerary,
      user_instruction: instruction,
      edit_scope: editScope.value,
      preserve_constraints: ["保留预算结构", "保留目的地和旅行日期"],
    });
    emit("updated", updatedItinerary);
    message.success("行程已智能调整。");
  } catch (error) {
    console.error(error);
    message.error("智能调整失败，请稍后再试。");
  } finally {
    editing.value = false;
  }
}
</script>

<template>
  <section v-if="itinerary" class="result-page">
    <aside class="sidebar-card">
      <div class="sidebar-card__title">行程导航</div>
      <ul class="sidebar-list">
        <li>行程概览</li>
        <li>预算明细</li>
        <li>按天花费</li>
        <li>智能调整</li>
        <li>景点地图</li>
        <li>天气信息</li>
        <li>餐饮住宿</li>
        <li>点位明细</li>
        <li>每日行程</li>
      </ul>

      <div class="sidebar-actions">
        <button class="back-button" @click="$emit('backHome')">返回规划页</button>
        <button class="save-button" :disabled="saving" @click="handleSave">
          {{ saving ? "保存中..." : "保存行程" }}
        </button>
        <button class="history-button" @click="$emit('viewHistory')">历史列表</button>
        <button class="export-button" :disabled="exportingPdf" @click="openPdfExport">
          {{ exportingPdf ? "准备 PDF..." : "导出 PDF" }}
        </button>
        <button
          class="export-button export-button--light"
          :disabled="exportingMarkdown"
          @click="openMarkdownExport"
        >
          {{ exportingMarkdown ? "准备中..." : "导出 Markdown" }}
        </button>
      </div>
    </aside>

    <div class="result-grid">
      <section class="result-card">
        <div class="result-card__title">{{ itinerary.destination }}旅行计划</div>
        <div class="info-row"><strong>行程 ID：</strong>{{ itinerary.trip_id }}</div>
        <div class="info-row">
          <strong>日期：</strong>
          {{ itinerary.days[0]?.date || "待定" }} 至
          {{ itinerary.days[itinerary.days.length - 1]?.date || "待定" }}
        </div>
        <div class="info-row"><strong>地点：</strong>{{ itinerary.destination }}</div>
        <div class="info-row summary-text">{{ itinerary.summary }}</div>
        <div v-if="displayTips.length" class="overview-tips">
          <div class="overview-tips__title">旅行提示</div>
          <ul>
            <li v-for="tip in displayTips" :key="tip">{{ tip }}</li>
          </ul>
        </div>
      </section>

      <section class="result-card">
        <div class="result-card__title">预算明细</div>
        <div class="budget-summary">
          <div class="budget-grid">
            <div v-for="item in budgetItems" :key="item.label" class="budget-box">
              <div class="budget-box__label">{{ item.label }}</div>
              <div class="budget-box__value">{{ item.value }}</div>
            </div>
          </div>
          <div class="budget-total">
            <span>总计</span>
            <strong>¥{{ itinerary.estimated_budget.toFixed(0) }}</strong>
          </div>
        </div>

        <div class="compact-weather">
          <div class="compact-weather__header">
            <span>天气信息</span>
            <small>{{ itinerary.destination }}</small>
          </div>
          <div v-if="weatherLoading" class="compact-weather__state">加载中...</div>
          <div v-else-if="weatherError" class="compact-weather__state">{{ weatherError }}</div>
          <div v-else-if="weather" class="compact-weather__list">
            <article
              v-for="day in weather.days"
              :key="`${day.date}-${day.week}`"
              class="compact-weather__item"
            >
              <span>{{ formatWeatherDate(day.date, day.week) }}</span>
              <strong>{{ day.day_temp || "-" }}°/{{ day.night_temp || "-" }}°</strong>
              <em>{{ day.day_weather || day.night_weather || "未知" }}</em>
            </article>
          </div>
          <div v-else class="compact-weather__state">暂无天气信息。</div>
        </div>
      </section>

      <section class="result-card result-card--map">
        <div class="map-card-header">
          <div class="result-card__title">景点地图</div>
          <button class="map-expand-button" type="button" @click="mapExpanded = true">
            放大查看
          </button>
        </div>
        <AmapTripMap :points="mapPoints" />
      </section>

      <Teleport to="body">
        <div v-if="mapExpanded" class="map-modal" @click.self="mapExpanded = false">
          <section class="map-modal__panel" role="dialog" aria-modal="true" aria-label="景点地图放大查看">
            <div class="map-modal__header">
              <div>
                <span>景点地图</span>
                <strong>{{ itinerary.destination }} · {{ mapPoints.length }} 个点位</strong>
              </div>
              <button class="map-modal__close" type="button" aria-label="关闭地图窗口" @click="mapExpanded = false">
                关闭
              </button>
            </div>
            <AmapTripMap :points="mapPoints" large />
          </section>
        </div>
      </Teleport>

      <section class="result-card result-card--full">
        <div class="result-card__title">智能调整行程</div>
        <div class="edit-panel">
          <div class="edit-panel__controls">
            <label class="edit-field">
              <span>调整范围</span>
              <select v-model="editScope">
                <option
                  v-for="day in itinerary.days"
                  :key="day.day_index"
                  :value="`day_${day.day_index}`"
                >
                  第{{ day.day_index }}天 · {{ day.theme || "未命名主题" }}
                </option>
              </select>
            </label>
            <button
              class="edit-submit-button"
              :disabled="editing"
              @click="handleEdit"
            >
              {{ editing ? "调整中..." : "智能调整" }}
            </button>
          </div>
          <textarea
            v-model="editInstruction"
            class="edit-textarea"
            rows="3"
            placeholder="例如：第二天轻松一点，不要安排太满；第三天想换成适合看日落的地点。"
          ></textarea>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">按天花费</div>
        <div class="day-budget-grid">
          <article
            v-for="item in dayBudgetItems"
            :key="item.key"
            class="day-budget-card"
          >
            <div class="day-budget-card__header">
              <span>{{ item.title }}</span>
              <span>{{ item.subtitle }}</span>
            </div>
            <div class="day-budget-card__body">
              <div class="day-budget-row">
                <span>门票</span>
                <strong>¥{{ item.tickets.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>餐饮</span>
                <strong>¥{{ item.meals.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>交通</span>
                <strong>¥{{ item.transport.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row">
                <span>住宿</span>
                <strong>¥{{ item.hotel.toFixed(0) }}</strong>
              </div>
              <div class="day-budget-row day-budget-row--total">
                <span>当日合计</span>
                <strong>¥{{ item.total.toFixed(0) }}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">住宿推荐</div>
        <div class="recommendation-grid">
          <article
            v-for="day in hotelRecommendationDays"
            :key="`hotel-recommend-${day.day_index}`"
            class="recommendation-card"
          >
            <div class="recommendation-card__header">
              <div>
                <span>第{{ day.day_index }}天</span>
                <strong>{{ day.theme || "当日推荐" }}</strong>
              </div>
              <span>{{ formatShortDate(day.date) }}</span>
            </div>

            <div class="recommendation-card__body">
              <div v-if="day.hotel" class="recommendation-item recommendation-item--hotel">
                <div
                  v-if="day.hotel.image_url"
                  class="recommendation-item__image"
                  :style="{ backgroundImage: `url(${day.hotel.image_url})` }"
                ></div>
                <div v-else class="recommendation-item__image recommendation-item__image--empty">
                  住宿
                </div>
                <div class="recommendation-item__content">
                  <div class="recommendation-item__eyebrow">住宿推荐</div>
                  <div class="recommendation-item__title">{{ day.hotel.name }}</div>
                  <div class="recommendation-item__reason">
                    {{ buildRecommendationReason(day.hotel, "hotel") }}
                  </div>
                  <div class="recommendation-meta">
                    <span>{{ formatMapRating(day.hotel.map_rating) }}</span>
                    <span>{{ formatReferenceCost(day.hotel.map_average_cost, day.hotel.estimated_cost) }}</span>
                    <span v-if="buildSourceText(day.hotel)">{{ buildSourceText(day.hotel) }}</span>
                    <span v-if="day.hotel.review_count != null">{{ day.hotel.review_count }} 条评价</span>
                    <span v-if="formatDistance(day.hotel.map_distance_meters)">
                      {{ formatDistance(day.hotel.map_distance_meters) }}
                    </span>
                  </div>
                  <div v-if="day.hotel.ranking_label" class="recommendation-tags">
                    {{ day.hotel.ranking_label }}
                  </div>
                  <div v-if="buildTagText(day.hotel.map_tags)" class="recommendation-tags">
                    {{ buildTagText(day.hotel.map_tags) }}
                  </div>
                  <div v-if="buildMapDetailText(day.hotel)" class="recommendation-map-detail">
                    {{ buildMapDetailText(day.hotel) }}
                  </div>
                  <div v-if="buildContactText(day.hotel)" class="recommendation-contact">
                    {{ buildContactText(day.hotel) }}
                  </div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">餐饮推荐</div>
        <div class="recommendation-grid">
          <article
            v-for="day in mealRecommendationDays"
            :key="`meal-recommend-${day.day_index}`"
            class="recommendation-card"
          >
            <div class="recommendation-card__header">
              <div>
                <span>第{{ day.day_index }}天</span>
                <strong>{{ day.theme || "当日推荐" }}</strong>
              </div>
              <span>{{ formatShortDate(day.date) }}</span>
            </div>

            <div class="recommendation-card__body">
              <div
                v-for="meal in day.visibleMeals"
                :key="`${day.day_index}-${meal.name}-${meal.meal_type}`"
                class="recommendation-item"
              >
                <div
                  v-if="meal.image_url"
                  class="recommendation-item__image"
                  :style="{ backgroundImage: `url(${meal.image_url})` }"
                ></div>
                <div v-else class="recommendation-item__image recommendation-item__image--empty">
                  餐饮
                </div>
                <div class="recommendation-item__content">
                  <div class="recommendation-item__eyebrow">{{ meal.meal_type }}推荐</div>
                  <div class="recommendation-item__title">{{ meal.name }}</div>
                  <div class="recommendation-item__reason">
                    {{ buildRecommendationReason(meal, "meal") }}
                  </div>
                  <div class="recommendation-meta">
                    <span>{{ formatMapRating(meal.map_rating) }}</span>
                    <span>{{ formatReferenceCost(meal.map_average_cost, meal.estimated_cost) }}</span>
                    <span v-if="buildSourceText(meal)">{{ buildSourceText(meal) }}</span>
                    <span v-if="meal.review_count != null">{{ meal.review_count }} 条评价</span>
                    <span v-if="formatDistance(meal.map_distance_meters)">
                      {{ formatDistance(meal.map_distance_meters) }}
                    </span>
                  </div>
                  <div v-if="meal.ranking_label" class="recommendation-tags">
                    {{ meal.ranking_label }}
                  </div>
                  <div v-if="buildTagText(meal.map_tags)" class="recommendation-tags">
                    {{ buildTagText(meal.map_tags) }}
                  </div>
                  <div v-if="buildMapDetailText(meal)" class="recommendation-map-detail">
                    {{ buildMapDetailText(meal) }}
                  </div>
                  <div v-if="buildContactText(meal)" class="recommendation-contact">
                    {{ buildContactText(meal) }}
                  </div>
                  <div v-if="meal.notes" class="recommendation-note">{{ meal.notes }}</div>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">地图点位明细</div>
        <div class="point-grid">
          <article v-for="point in scenicMapPoints" :key="point.key" class="point-card">
            <div class="point-card__header">
              <span>第{{ point.dayIndex }}天 · {{ point.name }}</span>
              <span>{{ formatShortDate(point.date) }}</span>
            </div>

            <div class="point-card__body">
              <div
                v-if="point.imageUrl"
                class="point-card__image"
                :style="{ backgroundImage: `url(${point.imageUrl})` }"
              ></div>
              <div v-else class="point-card__image point-card__image--empty">
                暂无景点图片
              </div>
              <div class="point-card__line">
                <strong>主题：</strong>
                <span>{{ point.theme }}</span>
              </div>
              <div class="point-card__line">
                <strong>地址：</strong>
                <span>{{ point.address }}</span>
              </div>
              <div class="point-meta">
                <span>{{ formatMapRating(point.rating) }}</span>
                <span>{{ formatReferenceCost(point.averageCost, point.estimatedCost) }}</span>
                <span v-if="formatDistance(point.distanceMeters)">
                  {{ formatDistance(point.distanceMeters) }}
                </span>
              </div>
              <div v-if="buildTagText(point.tags)" class="point-tags">
                {{ buildTagText(point.tags) }}
              </div>
              <div
                v-if="[point.businessArea, point.openTimeToday, point.type].filter(Boolean).length"
                class="point-card__line"
              >
                <strong>地图信息：</strong>
                <span>
                  {{
                    [
                      point.businessArea ? `${point.businessArea}商圈` : "",
                      point.openTimeToday ? `今日 ${point.openTimeToday}` : "",
                      point.type ? point.type.split(";").slice(-1)[0] : "",
                    ].filter(Boolean).join(" · ")
                  }}
                </span>
              </div>
              <div v-if="point.tel" class="point-card__line">
                <strong>电话：</strong>
                <span>{{ point.tel }}</span>
              </div>
              <div class="point-card__desc">{{ point.description }}</div>
            </div>
          </article>
        </div>
      </section>

      <section class="result-card result-card--full">
        <div class="result-card__title">每日行程</div>
        <div class="day-list">
          <details
            v-for="day in itinerary.days"
            :key="day.day_index"
            class="day-card"
            :open="day.day_index === 1"
          >
            <summary class="day-card__header">
              <span>第{{ day.day_index }}天 · {{ day.theme || "未命名主题" }}</span>
              <span class="day-card__meta">{{ formatShortDate(day.date) }}</span>
            </summary>

            <div class="day-card__body">
              <div class="day-card__section">
                <strong>主要景点：</strong>
                <span>
                  {{ day.spots[0]?.name || "未安排" }}
                  <em v-if="day.spots[0]?.map_rating"> · {{ formatMapRating(day.spots[0]?.map_rating) }}</em>
                </span>
              </div>
              <div class="day-card__section">
                <strong>景点地址：</strong>
                <span>{{ day.spots[0]?.address || day.spots[0]?.location || "待补充" }}</span>
              </div>
              <div class="day-card__section">
                <strong>餐饮建议：</strong>
                <span>
                  {{ day.meals[0]?.name || "未安排" }}
                  <em v-if="day.meals[0]?.map_average_cost">
                    · {{ formatReferenceCost(day.meals[0]?.map_average_cost, day.meals[0]?.estimated_cost) }}
                  </em>
                </span>
              </div>
              <div class="day-card__section">
                <strong>住宿安排：</strong>
                <span>
                  {{ day.hotel?.name || "未安排" }}
                  <em v-if="day.hotel?.map_rating"> · {{ formatMapRating(day.hotel?.map_rating) }}</em>
                  <em v-if="day.hotel?.map_average_cost">
                    · {{ formatReferenceCost(day.hotel?.map_average_cost, day.hotel?.estimated_cost) }}
                  </em>
                </span>
              </div>
              <div class="day-card__section">
                <strong>交通信息：</strong>
                <span>
                  {{
                    day.transport[0]?.distance_km != null
                      ? `${day.transport[0].distance_km.toFixed(2)} km / ${day.transport[0].estimated_minutes ?? 0} 分钟`
                      : day.transport[0]?.duration || "待补充"
                  }}
                </span>
              </div>
              <div class="day-card__section">
                <strong>备注：</strong>
                <span>{{ day.notes[day.notes.length - 1] || "无" }}</span>
              </div>
            </div>
          </details>
        </div>
      </section>
    </div>
  </section>

  <section v-else class="empty-state">
    <div class="empty-state__card">
      <h2>还没有生成结果</h2>
      <p>先回到规划页生成一条 itinerary，结果页就会开始展示真实数据。</p>
      <button class="back-button" @click="$emit('backHome')">返回规划页</button>
    </div>
  </section>
</template>

<style scoped>
.result-page {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 22px;
}

.sidebar-card,
.result-card,
.empty-state__card {
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 22px 55px rgba(98, 116, 164, 0.12);
  backdrop-filter: blur(14px);
}

.sidebar-card {
  align-self: start;
  padding: 18px;
}

.sidebar-card__title,
.result-card__title {
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6d82de 0%, #8a67cf 100%);
  color: #ffffff;
  font-size: 15px;
  font-weight: 700;
}

.sidebar-list {
  display: grid;
  gap: 12px;
  padding: 0;
  margin: 0 0 18px;
  list-style: none;
  color: #475467;
  font-size: 14px;
}

.sidebar-actions {
  display: grid;
  gap: 10px;
}

.back-button,
.save-button,
.history-button,
.export-button {
  width: 100%;
  border: none;
  border-radius: 14px;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.back-button {
  background: rgba(109, 130, 222, 0.12);
  color: #5d66c3;
}

.save-button {
  background: linear-gradient(135deg, #7386e0 0%, #8f71d8 100%);
  color: #ffffff;
}

.save-button:disabled {
  opacity: 0.7;
  cursor: wait;
}

.export-button:disabled {
  opacity: 0.7;
  cursor: wait;
}

.history-button {
  background: rgba(79, 70, 229, 0.1);
  color: #5b5bd6;
}

.export-button {
  background: rgba(59, 130, 246, 0.12);
  color: #3568d4;
}

.export-button--light {
  background: rgba(16, 185, 129, 0.12);
  color: #0f8c63;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.result-card {
  padding: 18px;
}

.result-card--map,
.result-card--weather {
  min-height: 330px;
}

.result-card--map {
  grid-column: 1 / -1;
  min-height: 520px;
}

.result-card--full {
  grid-column: 1 / -1;
}

.info-row {
  margin-bottom: 10px;
  color: #475467;
  line-height: 1.7;
}

.summary-text {
  margin-top: 14px;
}

.overview-tips {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(109, 130, 222, 0.08), rgba(138, 103, 207, 0.08));
  border: 1px solid rgba(98, 116, 164, 0.08);
}

.overview-tips__title {
  margin-bottom: 8px;
  color: #465467;
  font-weight: 800;
}

.overview-tips ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: #5d6675;
  line-height: 1.7;
}

.budget-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 148px;
  gap: 12px;
  align-items: stretch;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.budget-box {
  min-height: 82px;
  padding: 14px;
  border-radius: 16px;
  background: #f8faff;
  border: 1px solid rgba(98, 116, 164, 0.08);
}

.budget-box__label {
  color: #667085;
  font-size: 13px;
}

.budget-box__value {
  margin-top: 8px;
  color: #3b82f6;
  font-size: 21px;
  font-weight: 800;
}

.budget-total {
  display: grid;
  align-content: center;
  justify-items: end;
  min-height: 100%;
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, #7386e0 0%, #8f71d8 100%);
  color: #ffffff;
}

.budget-total span {
  font-size: 13px;
  font-weight: 800;
  opacity: 0.86;
}

.budget-total strong {
  margin-top: 8px;
  font-size: 30px;
  line-height: 1;
  text-align: right;
}

.compact-weather {
  margin-top: 14px;
  padding: 12px;
  border-radius: 16px;
  background: #f8faff;
  border: 1px solid rgba(98, 116, 164, 0.08);
}

.compact-weather__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  color: #465467;
  font-weight: 800;
}

.compact-weather__header small {
  color: #7b8494;
  font-size: 12px;
  font-weight: 700;
}

.compact-weather__state {
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.compact-weather__list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(124px, 1fr));
  gap: 8px;
}

.compact-weather__item {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid rgba(98, 116, 164, 0.08);
}

.compact-weather__item span,
.compact-weather__item em {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-weather__item strong {
  color: #3568d4;
  font-size: 16px;
  line-height: 1.2;
}

.map-card-header {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}

.map-card-header .result-card__title {
  flex: 1;
}

.map-expand-button,
.map-modal__close {
  border: none;
  border-radius: 14px;
  background: rgba(59, 130, 246, 0.12);
  color: #3568d4;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.map-expand-button {
  min-width: 92px;
  padding: 12px 14px;
}

.map-modal {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.52);
}

.map-modal__panel {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 14px;
  width: min(1180px, 100%);
  max-height: calc(100vh - 48px);
  padding: 18px;
  border-radius: 24px;
  background: #ffffff;
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.26);
}

.map-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.map-modal__header div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.map-modal__header span {
  color: #465467;
  font-size: 18px;
  font-weight: 900;
}

.map-modal__header strong {
  color: #667085;
  font-size: 13px;
}

.map-modal__close {
  flex: 0 0 auto;
  padding: 10px 14px;
}

.weather-state {
  color: #667085;
  line-height: 1.8;
}

.weather-grid {
  display: grid;
  gap: 12px;
}

.weather-card {
  padding: 14px;
  border-radius: 16px;
  background: #f8faff;
  border: 1px solid rgba(98, 116, 164, 0.08);
}

.weather-card__date {
  color: #465467;
  font-weight: 700;
}

.weather-card__temp {
  margin: 8px 0;
  color: #3b82f6;
  font-size: 24px;
  font-weight: 800;
}

.weather-card__desc {
  color: #667085;
  line-height: 1.7;
}

.edit-panel {
  display: grid;
  gap: 14px;
}

.edit-panel__controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px;
  gap: 12px;
  align-items: end;
}

.edit-field {
  display: grid;
  gap: 8px;
  color: #465467;
  font-weight: 700;
}

.edit-field select,
.edit-textarea {
  width: 100%;
  border: 1px solid rgba(98, 116, 164, 0.18);
  border-radius: 14px;
  background: #fbfcff;
  color: #334155;
  font: inherit;
  outline: none;
}

.edit-field select {
  min-height: 44px;
  padding: 0 14px;
}

.edit-textarea {
  resize: vertical;
  min-height: 92px;
  padding: 12px 14px;
  line-height: 1.7;
}

.edit-field select:focus,
.edit-textarea:focus {
  border-color: rgba(109, 130, 222, 0.65);
  box-shadow: 0 0 0 3px rgba(109, 130, 222, 0.12);
}

.edit-submit-button {
  min-height: 44px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #7386e0 0%, #8f71d8 100%);
  color: #ffffff;
  font-weight: 800;
  cursor: pointer;
}

.edit-submit-button:disabled {
  opacity: 0.7;
  cursor: wait;
}

.day-budget-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
}

.day-budget-card {
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(98, 116, 164, 0.08);
  background: #fbfcff;
}

.day-budget-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(109, 130, 222, 0.08);
  color: #465467;
  font-weight: 700;
}

.day-budget-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.day-budget-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #475467;
}

.day-budget-row--total {
  padding-top: 10px;
  border-top: 1px solid rgba(98, 116, 164, 0.08);
  color: #2f4fa5;
}

.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.recommendation-card {
  overflow: hidden;
  border: 1px solid rgba(98, 116, 164, 0.08);
  border-radius: 18px;
  background: #fbfcff;
}

.recommendation-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(109, 130, 222, 0.08);
  color: #667085;
}

.recommendation-card__header div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.recommendation-card__header strong {
  color: #465467;
  font-size: 15px;
}

.recommendation-card__body {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.recommendation-item {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 14px;
  padding: 12px;
  border: 1px solid rgba(98, 116, 164, 0.08);
  border-radius: 16px;
  background: #ffffff;
}

.recommendation-item--hotel {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.06), rgba(59, 130, 246, 0.05)), #ffffff;
}

.recommendation-item__image {
  min-height: 104px;
  border-radius: 12px;
  background-color: #eef3ff;
  background-position: center;
  background-size: cover;
}

.recommendation-item__image--empty {
  display: grid;
  place-items: center;
  color: #7b8494;
  font-weight: 800;
  background:
    linear-gradient(135deg, rgba(129, 179, 255, 0.18), rgba(16, 185, 129, 0.14)),
    #f7f9ff;
}

.recommendation-item__content {
  display: grid;
  align-content: start;
  gap: 7px;
  min-width: 0;
}

.recommendation-item__eyebrow {
  color: #5d66c3;
  font-size: 12px;
  font-weight: 800;
}

.recommendation-item__title {
  color: #334155;
  font-size: 16px;
  font-weight: 800;
  line-height: 1.35;
}

.recommendation-item__reason,
.recommendation-note,
.recommendation-contact,
.recommendation-map-detail {
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.recommendation-map-detail {
  color: #475467;
  font-weight: 700;
}

.recommendation-meta,
.point-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.recommendation-meta span,
.point-meta span {
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.1);
  color: #3568d4;
  font-size: 12px;
  font-weight: 800;
}

.recommendation-tags,
.point-tags {
  width: fit-content;
  max-width: 100%;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(16, 185, 129, 0.1);
  color: #0f8c63;
  font-size: 12px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.point-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}

.point-card {
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(98, 116, 164, 0.08);
  background: #fbfcff;
}

.point-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(109, 130, 222, 0.08);
  color: #465467;
  font-weight: 700;
}

.point-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.point-card__image {
  min-height: 150px;
  border-radius: 14px;
  background-position: center;
  background-size: cover;
  background-color: #eef3ff;
}

.point-card__image--empty {
  display: grid;
  place-items: center;
  color: #7b8494;
  font-weight: 700;
  background:
    linear-gradient(135deg, rgba(129, 179, 255, 0.18), rgba(137, 108, 230, 0.15)),
    #f7f9ff;
}

.point-card__line {
  color: #475467;
  line-height: 1.7;
}

.point-card__desc {
  padding-top: 10px;
  border-top: 1px solid rgba(98, 116, 164, 0.08);
  color: #667085;
  line-height: 1.7;
}

.day-list {
  display: grid;
  gap: 12px;
}

.day-card {
  border-radius: 18px;
  border: 1px solid rgba(98, 116, 164, 0.08);
  background: #fbfcff;
  overflow: hidden;
}

.day-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: rgba(109, 130, 222, 0.08);
  color: #465467;
  font-weight: 700;
  cursor: pointer;
  list-style: none;
}

.day-card__header::-webkit-details-marker {
  display: none;
}

.day-card__header::after {
  content: "展开";
  flex: 0 0 auto;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(109, 130, 222, 0.12);
  color: #5b5bd6;
  font-size: 12px;
}

.day-card[open] .day-card__header::after {
  content: "收起";
}

.day-card__meta {
  margin-left: auto;
  color: #667085;
  font-size: 13px;
}

.day-card__body {
  display: grid;
  gap: 10px;
  padding: 16px;
}

.day-card__section {
  color: #475467;
  line-height: 1.7;
}

.day-card__section em {
  color: #5d66c3;
  font-style: normal;
  font-weight: 700;
}

.empty-state {
  display: grid;
  place-items: center;
  min-height: 360px;
}

.empty-state__card {
  max-width: 560px;
  padding: 36px;
  text-align: center;
}

.empty-state__card h2 {
  margin: 0 0 12px;
}

.empty-state__card p {
  margin: 0 0 18px;
  color: #667085;
  line-height: 1.7;
}

@media (max-width: 960px) {
  .result-page {
    grid-template-columns: 1fr;
  }

  .result-grid {
    grid-template-columns: 1fr;
  }

  .edit-panel__controls {
    grid-template-columns: 1fr;
  }

  .budget-summary {
    grid-template-columns: 1fr;
  }

  .budget-total {
    justify-items: start;
  }

  .recommendation-grid {
    grid-template-columns: 1fr;
  }

  .recommendation-item {
    grid-template-columns: 1fr;
  }

  .recommendation-item__image {
    min-height: 150px;
  }

  .result-card--map {
    min-height: 420px;
  }

  .map-modal {
    padding: 12px;
  }

  .map-modal__panel {
    max-height: calc(100vh - 24px);
    padding: 14px;
    border-radius: 18px;
  }
}
</style>
