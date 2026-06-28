<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const emit = defineEmits<{
  startPlanning: [];
  viewHistory: [];
}>();

const { tm, t } = useI18n();

const capabilityItems = computed(() => tm("landing.capabilities") as Array<{
  label: string;
  value: string;
  description: string;
}>);
const workflowSteps = computed(() => tm("landing.workflowSteps") as string[]);
</script>

<template>
  <section class="landing-page">
    <nav class="landing-nav" :aria-label="t('landing.navLabel')">
      <div class="landing-nav__brand">VoyageOS</div>
      <div class="landing-nav__actions">
        <button class="landing-nav__link" @click="emit('viewHistory')">{{ t("landing.history") }}</button>
        <button class="landing-nav__button" @click="emit('startPlanning')">{{ t("landing.enter") }}</button>
      </div>
    </nav>

    <section class="landing-hero" aria-labelledby="landing-title">
      <div class="landing-hero__content">
        <div class="landing-hero__eyebrow">{{ t("landing.eyebrow") }}</div>
        <h1 id="landing-title" class="landing-hero__title">VoyageOS</h1>
        <p class="landing-hero__subtitle">
          {{ t("landing.subtitle") }}
        </p>
        <div class="landing-hero__actions">
          <button class="landing-button landing-button--primary" @click="emit('startPlanning')">
            {{ t("landing.enter") }}
          </button>
          <button class="landing-button landing-button--secondary" @click="emit('viewHistory')">
            {{ t("landing.viewHistory") }}
          </button>
        </div>
        <div class="landing-hero__metrics" :aria-label="t('landing.metricsLabel')">
          <div>
            <strong>4</strong>
            <span>{{ t("landing.metrics.views") }}</span>
          </div>
          <div>
            <strong>2</strong>
            <span>{{ t("landing.metrics.modes") }}</span>
          </div>
          <div>
            <strong>PDF</strong>
            <span>{{ t("landing.metrics.delivery") }}</span>
          </div>
        </div>
      </div>

      <div class="workspace-preview" :aria-label="t('landing.previewLabel')">
        <div class="workspace-preview__bar">
          <span></span>
          <span></span>
          <span></span>
          <strong>Live itinerary desk</strong>
        </div>
        <div class="destination-card">
          <div>
            <span class="preview-label">Destination</span>
            <h2>{{ t("landing.preview.title") }}</h2>
          </div>
          <div class="destination-card__badge">{{ t("landing.preview.draft") }}</div>
        </div>
        <div class="preview-grid">
          <div class="route-panel">
            <span class="preview-label">Route timeline</span>
            <div class="route-step route-step--active">
              <i></i>
              <div>
                <strong>Day 1</strong>
                <span>{{ t("landing.preview.day1") }}</span>
              </div>
            </div>
            <div class="route-step">
              <i></i>
              <div>
                <strong>Day 2</strong>
                <span>{{ t("landing.preview.day2") }}</span>
              </div>
            </div>
            <div class="route-step">
              <i></i>
              <div>
                <strong>Day 3</strong>
                <span>{{ t("landing.preview.day3") }}</span>
              </div>
            </div>
          </div>
          <div class="insight-panel">
            <div>
              <span class="preview-label">Budget</span>
              <strong>¥3200</strong>
            </div>
            <div>
              <span class="preview-label">Weather</span>
              <strong>22°C</strong>
            </div>
            <div>
              <span class="preview-label">POI</span>
              <strong>18+</strong>
            </div>
          </div>
        </div>
        <div class="map-strip">
          <span class="map-pin map-pin--one"></span>
          <span class="map-pin map-pin--two"></span>
          <span class="map-pin map-pin--three"></span>
        </div>
      </div>
    </section>

    <section class="capability-section" aria-labelledby="capability-title">
      <div class="section-heading">
        <span class="section-heading__kicker">Capability Matrix</span>
        <h2 id="capability-title">{{ t("landing.capabilitiesTitle") }}</h2>
      </div>
      <div class="capability-grid">
        <article v-for="item in capabilityItems" :key="item.label" class="capability-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.description }}</p>
        </article>
      </div>
    </section>

    <section class="workflow-section" :aria-label="t('landing.workflowLabel')">
      <div class="workflow-card">
        <span class="section-heading__kicker">Workflow</span>
        <h2>{{ t("landing.workflowTitle") }}</h2>
      </div>
      <div class="workflow-steps">
        <div v-for="(step, index) in workflowSteps" :key="step" class="workflow-step">
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          <strong>{{ step }}</strong>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
.landing-page {
  display: grid;
  gap: 32px;
}

.landing-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 14px 12px 18px;
  border: 1px solid rgba(22, 58, 54, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 18px 50px rgba(33, 61, 56, 0.08);
  backdrop-filter: blur(18px);
}

.landing-nav__brand {
  color: #173936;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 24px;
  font-weight: 800;
}

.landing-nav__actions {
  display: flex;
  gap: 10px;
}

.landing-nav__link,
.landing-nav__button,
.landing-button {
  border: 1px solid transparent;
  border-radius: 999px;
  font-weight: 800;
  cursor: pointer;
}

.landing-nav__link {
  padding: 10px 14px;
  background: transparent;
  color: #52645f;
}

.landing-nav__button {
  padding: 10px 16px;
  background: #173936;
  color: #ffffff;
}

.landing-hero {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(420px, 1.08fr);
  gap: 36px;
  align-items: center;
  min-height: calc(100vh - 116px);
  padding: 56px;
  border: 1px solid rgba(25, 66, 63, 0.1);
  border-radius: 32px;
  background:
    linear-gradient(130deg, rgba(255, 255, 255, 0.92) 0%, rgba(243, 248, 244, 0.82) 48%),
    radial-gradient(circle at 88% 14%, rgba(202, 167, 97, 0.24), transparent 26%);
  box-shadow: 0 30px 90px rgba(20, 42, 42, 0.12);
}

.landing-hero__content {
  max-width: 620px;
}

.landing-hero__eyebrow,
.section-heading__kicker,
.preview-label {
  color: #9a6b23;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.landing-hero__title {
  margin: 18px 0;
  color: #12312f;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 88px;
  line-height: 0.94;
  font-weight: 700;
}

.landing-hero__subtitle {
  max-width: 560px;
  margin: 0;
  color: #4b5d59;
  font-size: 20px;
  line-height: 1.75;
}

.landing-hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 34px;
}

.landing-button {
  min-height: 48px;
  padding: 0 22px;
  font-size: 15px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.landing-button:hover {
  transform: translateY(-2px);
}

.landing-button--primary {
  background: #143c38;
  color: #ffffff;
  box-shadow: 0 18px 36px rgba(20, 60, 56, 0.24);
}

.landing-button--secondary {
  border-color: rgba(20, 60, 56, 0.18);
  background: rgba(255, 255, 255, 0.72);
  color: #143c38;
}

.landing-hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 44px;
}

.landing-hero__metrics div {
  padding: 18px;
  border: 1px solid rgba(20, 60, 56, 0.1);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.68);
}

.landing-hero__metrics strong,
.landing-hero__metrics span {
  display: block;
}

.landing-hero__metrics strong {
  color: #143c38;
  font-size: 24px;
}

.landing-hero__metrics span {
  margin-top: 4px;
  color: #667570;
  font-size: 13px;
  font-weight: 700;
}

.workspace-preview {
  position: relative;
  display: grid;
  gap: 16px;
  min-height: 520px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 28px;
  background: #173f3b;
  box-shadow: 0 34px 80px rgba(17, 48, 45, 0.3);
  overflow: hidden;
}

.workspace-preview::before {
  content: "";
  position: absolute;
  inset: 56px -80px auto auto;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  background: rgba(208, 170, 92, 0.28);
  filter: blur(16px);
}

.workspace-preview__bar,
.destination-card,
.route-panel,
.insight-panel,
.map-strip {
  position: relative;
  z-index: 1;
}

.workspace-preview__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
}

.workspace-preview__bar span {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.32);
}

.workspace-preview__bar strong {
  margin-left: auto;
  font-weight: 700;
}

.destination-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 24px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.94);
}

.destination-card h2 {
  margin: 8px 0 0;
  color: #163936;
  font-size: 32px;
  line-height: 1.15;
}

.destination-card__badge {
  align-self: flex-start;
  border-radius: 999px;
  padding: 8px 12px;
  background: #d7ad58;
  color: #2b2112;
  font-size: 12px;
  font-weight: 900;
}

.preview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(150px, 0.75fr);
  gap: 16px;
}

.route-panel,
.insight-panel {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 22px;
  background: rgba(8, 32, 30, 0.72);
}

.route-panel {
  padding: 20px;
}

.route-step {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
  margin-top: 18px;
  color: rgba(255, 255, 255, 0.68);
}

.route-step i {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.32);
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.06);
}

.route-step--active i {
  background: #d9b15d;
  box-shadow: 0 0 0 6px rgba(217, 177, 93, 0.16);
}

.route-step strong,
.route-step span {
  display: block;
}

.route-step strong {
  color: #ffffff;
  font-size: 15px;
}

.route-step span {
  margin-top: 3px;
  font-size: 13px;
}

.insight-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.insight-panel div {
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.08);
}

.insight-panel strong {
  display: block;
  margin-top: 6px;
  color: #ffffff;
  font-size: 22px;
}

.map-strip {
  min-height: 132px;
  border-radius: 22px;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(135deg, rgba(217, 177, 93, 0.24), rgba(255, 255, 255, 0.06));
  background-size:
    34px 34px,
    34px 34px,
    auto;
}

.map-pin {
  position: absolute;
  width: 13px;
  height: 13px;
  border: 3px solid #ffffff;
  border-radius: 999px;
  background: #d9b15d;
  box-shadow: 0 0 0 8px rgba(217, 177, 93, 0.14);
}

.map-pin--one {
  left: 18%;
  top: 34%;
}

.map-pin--two {
  left: 52%;
  top: 56%;
}

.map-pin--three {
  right: 18%;
  top: 28%;
}

.section-heading {
  max-width: 780px;
}

.section-heading h2,
.workflow-card h2 {
  margin: 10px 0 0;
  color: #173936;
  font-family: Georgia, "Times New Roman", "Songti SC", serif;
  font-size: 40px;
  line-height: 1.14;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

.capability-card,
.workflow-card,
.workflow-step {
  border: 1px solid rgba(25, 66, 63, 0.1);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 22px 55px rgba(34, 61, 57, 0.08);
  backdrop-filter: blur(14px);
}

.capability-card {
  min-height: 194px;
  padding: 22px;
  border-radius: 20px;
}

.capability-card span,
.capability-card strong,
.capability-card p {
  display: block;
}

.capability-card span {
  color: #9a6b23;
  font-size: 12px;
  font-weight: 900;
}

.capability-card strong {
  margin-top: 14px;
  color: #153c38;
  font-size: 20px;
}

.capability-card p {
  margin: 12px 0 0;
  color: #5f6e6a;
  font-size: 14px;
  line-height: 1.7;
}

.workflow-section {
  display: grid;
  grid-template-columns: minmax(280px, 0.78fr) minmax(0, 1.22fr);
  gap: 16px;
}

.workflow-card,
.workflow-step {
  border-radius: 22px;
}

.workflow-card {
  padding: 26px;
}

.workflow-card h2 {
  font-size: 34px;
}

.workflow-steps {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.workflow-step {
  min-height: 132px;
  padding: 22px;
}

.workflow-step span {
  display: block;
  color: #ba8730;
  font-size: 13px;
  font-weight: 900;
}

.workflow-step strong {
  display: block;
  margin-top: 20px;
  color: #173936;
  font-size: 18px;
  line-height: 1.45;
}

@media (max-width: 980px) {
  .landing-hero,
  .workflow-section {
    grid-template-columns: 1fr;
  }

  .landing-hero {
    min-height: auto;
    padding: 36px;
  }

  .landing-hero__title {
    font-size: 68px;
  }

  .workspace-preview {
    min-height: auto;
  }

  .capability-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .landing-page {
    gap: 24px;
  }

  .landing-nav {
    display: grid;
  }

  .landing-nav__actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }

  .landing-hero {
    padding: 26px 18px;
    border-radius: 24px;
  }

  .landing-hero__title {
    font-size: 48px;
  }

  .landing-hero__subtitle {
    font-size: 16px;
  }

  .landing-hero__metrics,
  .preview-grid,
  .capability-grid,
  .workflow-steps {
    grid-template-columns: 1fr;
  }

  .workspace-preview {
    padding: 14px;
    border-radius: 22px;
  }

  .destination-card {
    display: grid;
  }

  .destination-card h2,
  .section-heading h2,
  .workflow-card h2 {
    font-size: 30px;
  }

  .landing-button {
    width: 100%;
  }
}
</style>
