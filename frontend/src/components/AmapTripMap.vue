<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

interface TripMapPoint {
  key: string;
  kind?: "spot" | "hotel" | "meal";
  label?: string;
  recommended?: boolean;
  dayIndex: number;
  date: string;
  theme: string;
  name: string;
  address: string;
  latitude: number | null | undefined;
  longitude: number | null | undefined;
  poiId: string | null | undefined;
  imageUrl?: string | null;
  description: string;
  rating?: number | null;
  averageCost?: number | null;
  estimatedCost?: number | null;
  tags?: string[];
  distanceMeters?: number | null;
}

const props = defineProps<{
  points: TripMapPoint[];
  large?: boolean;
}>();
const { t } = useI18n();

declare global {
  interface Window {
    AMap?: any;
  }
}

const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = ref<any>(null);
const markerList = ref<any[]>([]);
const routeLine = ref<any>(null);
const loadError = ref("");
const activeKind = ref<"spot" | "hotel" | "meal">("spot");
const activeDayIndex = ref<number | null>(null);

const amapKey = import.meta.env.VITE_AMAP_JS_KEY;

const validPoints = computed(() =>
  props.points.filter(
    (point) => point.longitude != null && point.latitude != null
  )
);

const visiblePoints = computed(() =>
  validPoints.value.filter((point) => {
    const matchesKind = (point.kind || "spot") === activeKind.value;
    const matchesDay = activeDayIndex.value == null || point.dayIndex === activeDayIndex.value;
    return matchesKind && matchesDay;
  })
);

const filterOptions = computed(() => [
  {
    key: "spot" as const,
    label: t("map.categories.spot"),
    count: validPoints.value.filter((point) => (point.kind || "spot") === "spot").length,
  },
  {
    key: "hotel" as const,
    label: t("map.categories.hotel"),
    count: validPoints.value.filter((point) => point.kind === "hotel").length,
  },
  {
    key: "meal" as const,
    label: t("map.categories.meal"),
    count: validPoints.value.filter((point) => point.kind === "meal").length,
  },
]);

const dayOptionsByKind = computed(() => {
  const groups: Record<"spot" | "hotel" | "meal", { dayIndex: number; count: number }[]> = {
    spot: [],
    hotel: [],
    meal: [],
  };
  const dayCounts: Record<"spot" | "hotel" | "meal", Map<number, number>> = {
    spot: new Map(),
    hotel: new Map(),
    meal: new Map(),
  };

  validPoints.value.forEach((point) => {
    const kind = point.kind || "spot";
    dayCounts[kind].set(point.dayIndex, (dayCounts[kind].get(point.dayIndex) || 0) + 1);
  });

  (Object.keys(dayCounts) as Array<"spot" | "hotel" | "meal">).forEach((kind) => {
    groups[kind] = [...dayCounts[kind].entries()]
      .sort(([dayA], [dayB]) => dayA - dayB)
      .map(([dayIndex, count]) => ({ dayIndex, count }));
  });

  return groups;
});

function selectKind(kind: "spot" | "hotel" | "meal") {
  activeKind.value = kind;
  activeDayIndex.value = null;
}

function selectDay(kind: "spot" | "hotel" | "meal", dayIndex: number) {
  activeKind.value = kind;
  activeDayIndex.value = dayIndex;
}

function escapeHtml(value: string | number | null | undefined): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatRating(value?: number | null): string {
  return value != null ? t("common.rating", { value: value.toFixed(1) }) : "";
}

function formatCost(value?: number | null, fallback?: number | null): string {
  if (value != null) {
    return t("common.referencePrice", { value: value.toFixed(0) });
  }
  if (fallback != null) {
    return t("common.budgetPrice", { value: fallback.toFixed(0) });
  }
  return "";
}

function formatDistance(value?: number | null): string {
  if (value == null) {
    return "";
  }
  return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value.toFixed(0)} m`;
}

function getPointVisual(point: TripMapPoint) {
  if (point.kind === "hotel") {
    return {
      icon: "🏨",
      badge: t("map.recommendedHotel"),
      color: "#059669",
      gradient: "linear-gradient(135deg,#10b981,#059669)",
      soft: "rgba(16,185,129,0.12)",
    };
  }

  if (point.kind === "meal") {
    return {
      icon: "🍽",
      badge: point.label || t("map.recommendedMeal"),
      color: "#d97706",
      gradient: "linear-gradient(135deg,#f59e0b,#d97706)",
      soft: "rgba(245,158,11,0.12)",
    };
  }

  return {
    icon: "🚩",
    badge: `D${point.dayIndex}`,
    color: "#143c38",
    gradient: "linear-gradient(135deg,#143c38,#1f574f)",
    soft: "rgba(20,60,56,0.12)",
  };
}

function clearOverlays() {
  if (!mapInstance.value) {
    return;
  }

  markerList.value.forEach((marker) => {
    mapInstance.value.remove(marker);
  });
  markerList.value = [];

  if (routeLine.value) {
    mapInstance.value.remove(routeLine.value);
    routeLine.value = null;
  }
}

function renderMarkers() {
  if (!window.AMap || !mapInstance.value) {
    return;
  }

  clearOverlays();

  const kindOrder = { spot: 0, hotel: 1, meal: 2 };
  const sorted = [...visiblePoints.value].sort((a, b) => {
    const dayDiff = a.dayIndex - b.dayIndex;
    if (dayDiff !== 0) {
      return dayDiff;
    }
    return (kindOrder[a.kind || "spot"] ?? 0) - (kindOrder[b.kind || "spot"] ?? 0);
  });
  const bounds: [number, number][] = [];
  const routePath: [number, number][] = [];

  sorted.forEach((point) => {
    const position: [number, number] = [point.longitude as number, point.latitude as number];
    const visual = getPointVisual(point);
    const isRecommendedPoi = point.recommended && point.kind !== "spot";
    const safeName = escapeHtml(point.name);
    const safeAddress = escapeHtml(point.address);
    const safeTheme = escapeHtml(point.theme);
    const safeLabel = escapeHtml(point.label || visual.badge);
    const safeDescription = escapeHtml(point.description);
    const metaItems = [
      formatRating(point.rating),
      formatCost(point.averageCost, point.estimatedCost),
      formatDistance(point.distanceMeters),
      ...(point.tags || []).slice(0, 2),
    ].filter(Boolean);
    bounds.push(position);
    if ((point.kind || "spot") === "spot") {
      routePath.push(position);
    }

    const marker = new window.AMap.Marker({
      position,
      title: point.name,
      offset: new window.AMap.Pixel(-12, -28),
      content: `
        <div style="position:relative;display:flex;flex-direction:column;align-items:center;">
          <div style="
            display:grid;
            place-items:center;
            width:${isRecommendedPoi ? "34px" : "28px"};
            height:${isRecommendedPoi ? "34px" : "28px"};
            border:${isRecommendedPoi ? "3px solid #fff" : "2px solid #fff"};
            border-radius:999px;
            background:${visual.gradient};
            box-shadow:${isRecommendedPoi ? "0 8px 18px rgba(15,23,42,0.26)" : "0 4px 10px rgba(15,23,42,0.18)"};
            font-size:${isRecommendedPoi ? "19px" : "16px"};
            line-height:1;
          ">${visual.icon}</div>
          <div style="
            margin-top:2px;
            padding:${isRecommendedPoi ? "3px 9px" : "2px 7px"};
            border-radius:999px;
            background:${visual.gradient};
            color:#fff;
            font-size:11px;
            font-weight:800;
            white-space:nowrap;
            box-shadow:0 2px 6px rgba(0,0,0,0.18);
          ">${escapeHtml(visual.badge)}</div>
        </div>
      `,
      zIndex: isRecommendedPoi ? 180 : 120,
    });

    const imageHtml = point.imageUrl
      ? `<img src="${escapeHtml(point.imageUrl)}" alt="${safeName}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;" />`
      : `<div style="width:100%;height:100%;display:grid;place-items:center;border-radius:8px;background:${visual.soft};color:${visual.color};font-size:11px;font-weight:800;">${safeLabel}</div>`;

    const bubble = new window.AMap.Marker({
      position,
      offset: new window.AMap.Pixel(isRecommendedPoi ? 18 : 14, isRecommendedPoi ? -58 : -46),
      content: `
        <div style="
          position:relative;
          width:${isRecommendedPoi ? "138px" : "110px"};
          background:#fff;
          border:${isRecommendedPoi ? `2px solid ${visual.color}` : "1px solid rgba(15,23,42,0.06)"};
          border-radius:12px;
          box-shadow:${isRecommendedPoi ? "0 10px 26px rgba(15,23,42,0.2)" : "0 3px 12px rgba(0,0,0,0.12)"};
          overflow:hidden;
          font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        ">
          <div style="width:100%;height:${isRecommendedPoi ? "84px" : "72px"};overflow:hidden;background:rgba(238,246,241,0.9);">
            ${imageHtml}
          </div>
          <div style="padding:${isRecommendedPoi ? "7px 9px 8px" : "5px 8px 6px"};">
            <div style="display:flex;align-items:center;gap:5px;margin-bottom:4px;">
              <span style="padding:2px 6px;border-radius:999px;background:${visual.soft};color:${visual.color};font-size:10px;font-weight:900;white-space:nowrap;">${safeLabel}</span>
              <span style="color:#8a94a6;font-size:10px;white-space:nowrap;">D${point.dayIndex}</span>
            </div>
            <div style="font-size:${isRecommendedPoi ? "13px" : "11px"};font-weight:800;color:#2d3748;line-height:1.3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${safeName}</div>
            ${
              metaItems.length
                ? `<div style="margin-top:4px;color:#63726e;font-size:10px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(metaItems.join(" · "))}</div>`
                : ""
            }
          </div>
          <div style="
            position:absolute;
            left:-5px;
            top:${isRecommendedPoi ? "42px" : "30px"};
            width:0;
            height:0;
            border-top:5px solid transparent;
            border-bottom:5px solid transparent;
            border-right:5px solid ${isRecommendedPoi ? visual.color : "#fff"};
            filter:drop-shadow(-2px 0 2px rgba(0,0,0,0.06));
          "></div>
        </div>
      `,
      zIndex: isRecommendedPoi ? 170 : 100,
    });

    const infoWindow = new window.AMap.InfoWindow({
      offset: new window.AMap.Pixel(0, -32),
      content: `
        <div style="max-width:240px;padding:4px 2px;line-height:1.7;">
          <strong>${safeName}</strong><br/>
          <span>${escapeHtml(t("map.infoLine", { label: safeLabel, day: point.dayIndex, theme: safeTheme }))}</span><br/>
          <span>${safeAddress}</span>
          ${safeDescription ? `<br/><span>${safeDescription}</span>` : ""}
        </div>
      `,
    });

    marker.on("click", () => {
      infoWindow.open(mapInstance.value, position);
    });

    mapInstance.value.add(marker);
    mapInstance.value.add(bubble);
    markerList.value.push(marker);
    markerList.value.push(bubble);
  });

  if (routePath.length >= 2) {
    routeLine.value = new window.AMap.Polyline({
      path: routePath,
      strokeColor: "#8f661f",
      strokeWeight: 3,
      strokeOpacity: 0.8,
      strokeStyle: "dashed",
      strokeDasharray: [10, 6],
      lineJoin: "round",
      lineCap: "round",
      showDir: true,
      dirColor: "#8f661f",
      dirSize: 8,
      borderWeight: 1,
      borderColor: "rgba(143,102,31,0.25)",
      zIndex: 50,
    });
    mapInstance.value.add(routeLine.value);
  }

  if (bounds.length === 1) {
    mapInstance.value.setZoomAndCenter(13, bounds[0]);
  } else if (bounds.length > 1) {
    mapInstance.value.setFitView(markerList.value, false, [60, 60, 60, 60]);
  }
}

function ensureMapScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.AMap) {
      resolve();
      return;
    }

    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[data-amap-loader="true"]'
    );

    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error(t("map.errors.script"))), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${amapKey}`;
    script.async = true;
    script.defer = true;
    script.dataset.amapLoader = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(t("map.errors.script")));
    document.head.appendChild(script);
  });
}

async function initMap() {
  if (!amapKey) {
    loadError.value = t("map.errors.missingKey");
    return;
  }

  if (!mapContainer.value) {
    return;
  }

  try {
    loadError.value = "";
    await ensureMapScript();

    if (!window.AMap) {
      loadError.value = t("map.errors.init");
      return;
    }

    mapInstance.value = new window.AMap.Map(mapContainer.value, {
      zoom: 11,
      resizeEnable: true,
      viewMode: "2D",
      mapStyle: "amap://styles/whitesmoke",
    });

    renderMarkers();
  } catch (error) {
    console.error(error);
    loadError.value = t("map.errors.load");
  }
}

onMounted(() => {
  void initMap();
});

watch([visiblePoints, activeKind, activeDayIndex], () => {
  if (mapInstance.value) {
    renderMarkers();
  }
});

onBeforeUnmount(() => {
  clearOverlays();
  if (mapInstance.value) {
    mapInstance.value.destroy();
    mapInstance.value = null;
  }
});
</script>

<template>
  <div class="trip-map" :class="{ 'trip-map--large': large }">
    <div v-if="loadError" class="trip-map__placeholder">
      <strong>{{ t("map.disabledTitle") }}</strong>
      <span>{{ loadError }}</span>
    </div>
    <div v-else-if="validPoints.length === 0" class="trip-map__placeholder">
      <strong>{{ t("map.emptyTitle") }}</strong>
      <span>{{ t("map.emptyDescription") }}</span>
    </div>
    <div v-else class="trip-map__stage">
      <div class="trip-map__filters" :aria-label="t('map.filtersLabel')">
        <div
          v-for="option in filterOptions"
          :key="option.key"
          class="trip-map__filter-group"
        >
          <button
            class="trip-map__filter"
            :class="{ 'trip-map__filter--active': activeKind === option.key }"
            type="button"
            :disabled="option.count === 0"
            @click="selectKind(option.key)"
          >
            <span>{{ option.label }}</span>
            <strong>{{ option.count }}</strong>
          </button>
          <div
            v-if="dayOptionsByKind[option.key].length > 0"
            class="trip-map__day-menu"
            :aria-label="t('map.filterByDay', { label: option.label })"
          >
            <button
              v-for="dayOption in dayOptionsByKind[option.key]"
              :key="dayOption.dayIndex"
              class="trip-map__day-filter"
              :class="{
                'trip-map__day-filter--active':
                  activeKind === option.key && activeDayIndex === dayOption.dayIndex,
              }"
              type="button"
              @click="selectDay(option.key, dayOption.dayIndex)"
            >
              <span>{{ t("map.dayLabel", { index: dayOption.dayIndex }) }}</span>
              <strong>{{ dayOption.count }}</strong>
            </button>
          </div>
        </div>
      </div>
      <div v-if="visiblePoints.length === 0" class="trip-map__empty-filter">
        {{ t("map.emptyFilter") }}
      </div>
      <div ref="mapContainer" class="trip-map__canvas"></div>
    </div>
  </div>
</template>

<style scoped>
.trip-map {
  height: calc(100% - 58px);
  min-height: 280px;
}

.trip-map--large {
  height: min(72vh, 760px);
  min-height: 520px;
}

.trip-map__stage,
.trip-map__canvas,
.trip-map__placeholder {
  width: 100%;
  height: 100%;
  min-height: 280px;
  border-radius: 20px;
}

.trip-map__stage {
  position: relative;
  overflow: hidden;
}

.trip-map__canvas {
  position: absolute;
  inset: 0;
}

.trip-map__filters {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-width: calc(100% - 28px);
}

.trip-map__filter-group {
  position: relative;
}

.trip-map__filter {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid rgba(25, 66, 63, 0.16);
  border-radius: 999px;
  padding: 8px 11px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.12);
  color: #314844;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.trip-map__day-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 25;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 92px;
  max-height: min(320px, calc(100vh - 220px));
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px;
  border: 1px solid rgba(25, 66, 63, 0.14);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition:
    opacity 0.16s ease,
    transform 0.16s ease;
}

.trip-map__day-menu::-webkit-scrollbar {
  width: 6px;
}

.trip-map__day-menu::-webkit-scrollbar-track {
  border-radius: 999px;
  background: rgba(25, 66, 63, 0.08);
}

.trip-map__day-menu::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(20, 60, 56, 0.42);
}

.trip-map__filter-group:hover .trip-map__day-menu,
.trip-map__filter-group:focus-within .trip-map__day-menu {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.trip-map__day-filter {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  border: 0;
  border-radius: 999px;
  padding: 7px 9px;
  background: rgba(250, 251, 247, 0.92);
  color: #314844;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
}

.trip-map__day-filter strong {
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  border-radius: 999px;
  background: rgba(20, 60, 56, 0.1);
  color: #63726e;
  font-size: 10px;
}

.trip-map__day-filter--active {
  background: linear-gradient(135deg, rgba(20, 60, 56, 0.96), rgba(31, 87, 79, 0.96));
  color: #ffffff;
}

.trip-map__day-filter--active strong {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.trip-map__filter strong {
  display: grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  border-radius: 999px;
  background: rgba(20, 60, 56, 0.1);
  color: #63726e;
  font-size: 11px;
}

.trip-map__filter--active {
  border-color: rgba(20, 60, 56, 0.18);
  background: linear-gradient(135deg, #143c38, #1f574f);
  color: #ffffff;
}

.trip-map__filter--active strong {
  background: rgba(255, 255, 255, 0.2);
  color: #ffffff;
}

.trip-map__filter:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.trip-map__empty-filter {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 15;
  transform: translate(-50%, -50%);
  border-radius: 999px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.14);
  color: #63726e;
  font-size: 13px;
  font-weight: 800;
}

.trip-map__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 20px;
  background:
    linear-gradient(135deg, rgba(20, 60, 56, 0.14), rgba(215, 173, 88, 0.16)),
    linear-gradient(45deg, rgba(255, 255, 255, 0.75), rgba(250, 251, 247, 0.9));
  color: #314844;
  text-align: center;
}

.trip-map__placeholder strong {
  font-size: 22px;
  color: #143c38;
}

.trip-map__placeholder span {
  max-width: 360px;
  color: #63726e;
  line-height: 1.7;
}

@media (max-width: 720px) {
  .trip-map--large {
    height: 68vh;
    min-height: 420px;
  }
}
</style>
