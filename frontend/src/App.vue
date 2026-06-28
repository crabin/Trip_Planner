<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import type { Itinerary, TripDetailResponse } from "./types";
import FloatingChatbot from "./components/FloatingChatbot.vue";
import DeepPlanResult from "./views/DeepPlanResult.vue";
import History from "./views/History.vue";
import Home from "./views/Home.vue";
import Landing from "./views/Landing.vue";
import Result from "./views/Result.vue";
import { DEFAULT_LOCALE, LOCALE_STORAGE_KEY, type Locale } from "./i18n";

const currentView = ref<"landing" | "home" | "result" | "history" | "deep-result">("landing");
const latestItinerary = ref<Itinerary | null>(null);
const latestDeepPlan = ref<TripDetailResponse | null>(null);
const { locale, t } = useI18n();

const currentLocale = computed({
  get: () => locale.value as Locale,
  set: (nextLocale: Locale) => {
    locale.value = nextLocale;
  },
});

const languageOptions = computed(() => [
  { label: t("app.language.chinese"), value: "zh-CN" },
  { label: t("app.language.english"), value: "en-US" },
]);

watch(
  currentLocale,
  (nextLocale) => {
    document.documentElement.lang = nextLocale;
    document.title = t("app.documentTitle");
    window.localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale);
  },
  { immediate: true },
);

if (!currentLocale.value) {
  currentLocale.value = DEFAULT_LOCALE;
}

function handleGenerated(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function openTrip(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}

function openDeepPlan(detail: TripDetailResponse) {
  latestDeepPlan.value = detail;
  currentView.value = "deep-result";
}

function updateCurrentItinerary(itinerary: Itinerary) {
  latestItinerary.value = itinerary;
  currentView.value = "result";
}
</script>

<template>
  <div class="app-shell">
    <div class="app-shell__glow app-shell__glow--left"></div>
    <div class="app-shell__glow app-shell__glow--right"></div>

    <div class="language-switcher" :aria-label="t('app.language.label')">
      <a-segmented v-model:value="currentLocale" :options="languageOptions" />
    </div>

    <header v-if="currentView !== 'landing'" class="hero">
      <div class="hero__badge">{{ t("app.badge") }}</div>
      <h1 class="hero__title">{{ t("app.title") }}</h1>

      <div class="hero__tabs">
        <button
          :class="['hero__tab', { 'hero__tab--active': currentView === 'home' }]"
          @click="currentView = 'home'"
        >
          {{ t("app.nav.planner") }}
        </button>
        <button
          :class="[
            'hero__tab',
            { 'hero__tab--active': currentView === 'result' },
            { 'hero__tab--disabled': !latestItinerary }
          ]"
          :disabled="!latestItinerary"
          @click="currentView = 'result'"
        >
          {{ t("app.nav.result") }}
        </button>
        <button
          :class="[
            'hero__tab',
            { 'hero__tab--active': currentView === 'deep-result' },
            { 'hero__tab--disabled': !latestDeepPlan }
          ]"
          :disabled="!latestDeepPlan"
          @click="currentView = 'deep-result'"
        >
          {{ t("app.nav.deepPlan") }}
        </button>
        <button
          :class="['hero__tab', { 'hero__tab--active': currentView === 'history' }]"
          @click="currentView = 'history'"
        >
          {{ t("app.nav.history") }}
        </button>
      </div>
    </header>

    <main class="page-content">
      <Landing
        v-if="currentView === 'landing'"
        @start-planning="currentView = 'home'"
        @view-history="currentView = 'history'"
      />
      <Home
        v-else-if="currentView === 'home'"
        @generated="handleGenerated"
        @deep-submitted="currentView = 'history'"
      />
      <Result
        v-else-if="currentView === 'result'"
        :itinerary="latestItinerary"
        @back-home="currentView = 'home'"
        @view-history="currentView = 'history'"
        @updated="updateCurrentItinerary"
      />
      <History
        v-else-if="currentView === 'history'"
        :active="currentView === 'history'"
        @open-trip="openTrip"
        @open-deep-plan="openDeepPlan"
      />
      <DeepPlanResult
        v-else
        :detail="latestDeepPlan"
        @back-home="currentView = 'home'"
        @open-trip="openTrip"
        @view-history="currentView = 'history'"
      />
    </main>

    <FloatingChatbot
      :current-itinerary="latestItinerary"
      :locale="currentLocale"
      @itinerary-updated="updateCurrentItinerary"
    />
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  min-width: 320px;
  font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at 12% 8%, rgba(221, 190, 123, 0.25), transparent 28%),
    radial-gradient(circle at 88% 18%, rgba(84, 129, 118, 0.2), transparent 24%),
    linear-gradient(180deg, #f5f4ee 0%, #edf3ef 48%, #e9efec 100%);
  color: #1b2f2d;
}

:global(*) {
  box-sizing: border-box;
}

.app-shell {
  position: relative;
  min-height: 100vh;
  padding: 28px 24px 64px;
  overflow: hidden;
}

.app-shell__glow {
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  filter: blur(24px);
  opacity: 0.5;
  pointer-events: none;
}

.app-shell__glow--left {
  top: -110px;
  left: -90px;
  background: rgba(207, 166, 83, 0.26);
}

.app-shell__glow--right {
  right: -80px;
  bottom: 120px;
  background: rgba(33, 91, 84, 0.18);
}

.language-switcher {
  position: fixed;
  top: 18px;
  right: 22px;
  z-index: 20;
  padding: 4px;
  border: 1px solid rgba(22, 58, 54, 0.1);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 14px 36px rgba(33, 61, 56, 0.12);
  backdrop-filter: blur(16px);
}

.language-switcher :deep(.ant-segmented) {
  background: transparent;
}

.language-switcher :deep(.ant-segmented-item) {
  color: #52645f;
  font-weight: 800;
}

.language-switcher :deep(.ant-segmented-item-selected) {
  background: #173936;
  color: #ffffff;
}

.hero {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 0 auto 22px;
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  padding: 9px 14px;
  border-radius: 999px;
  border: 1px solid rgba(22, 58, 54, 0.1);
  background: rgba(255, 255, 255, 0.74);
  color: #8d641f;
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0;
  box-shadow: 0 12px 30px rgba(36, 62, 58, 0.08);
}

.hero__title {
  margin: 0;
  color: #173936;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 34px;
  line-height: 1.1;
}

.hero::before {
  content: "";
  position: absolute;
  inset: -12px -18px -12px;
  z-index: -1;
  border: 1px solid rgba(22, 58, 54, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 18px 50px rgba(33, 61, 56, 0.08);
  backdrop-filter: blur(18px);
}

.hero__tabs {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px;
  border: 1px solid rgba(22, 58, 54, 0.08);
  border-radius: 16px;
  background: rgba(238, 242, 235, 0.72);
  backdrop-filter: blur(10px);
}

.hero__tab {
  border: none;
  border-radius: 10px;
  padding: 10px 18px;
  background: transparent;
  color: #52645f;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
}

.hero__tab--active {
  background: #173936;
  color: #ffffff;
  box-shadow: 0 10px 24px rgba(23, 57, 54, 0.14);
}

.hero__tab--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-content {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .app-shell {
    padding: 64px 16px 40px;
  }

  .language-switcher {
    top: 14px;
    right: 16px;
  }

  .hero {
    display: grid;
    justify-items: start;
    margin-bottom: 18px;
  }

  .hero__title {
    font-size: 28px;
  }

  .hero::before {
    inset: -10px -10px -10px;
  }

  .hero__tabs {
    width: 100%;
  }

  .hero__tab {
    flex: 1 1 42%;
    padding-inline: 10px;
  }
}
</style>
