<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { Itinerary } from "../types";
import { mountFloatingChatbot } from "./FloatingChatbotReact";

const props = defineProps<{
  currentItinerary?: Itinerary | null;
}>();

const emit = defineEmits<{
  itineraryUpdated: [itinerary: Itinerary];
}>();

const mountPoint = ref<HTMLElement | null>(null);
let chatbotHandle: ReturnType<typeof mountFloatingChatbot> | null = null;

onMounted(() => {
  if (mountPoint.value) {
    chatbotHandle = mountFloatingChatbot(mountPoint.value, {
      currentItinerary: props.currentItinerary ?? null,
      onItineraryUpdated: (itinerary) => emit("itineraryUpdated", itinerary),
    });
  }
});

watch(
  () => props.currentItinerary,
  (itinerary) => {
    chatbotHandle?.update({
      currentItinerary: itinerary ?? null,
      onItineraryUpdated: (updatedItinerary) => emit("itineraryUpdated", updatedItinerary),
    });
  },
  { deep: true },
);

onBeforeUnmount(() => {
  chatbotHandle?.unmount();
  chatbotHandle = null;
});
</script>

<template>
  <div ref="mountPoint" class="floating-chatbot-host"></div>
</template>

<style>
html {
  height: auto;
  min-height: 100%;
}

body {
  height: auto;
  min-height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
}

.floating-chatbot-host {
  position: fixed;
  left: 24px;
  bottom: 24px;
  z-index: 30;
  pointer-events: none;
}

.floating-chatbot {
  --floating-chatbot-width: 380px;
  --floating-chatbot-height: 560px;
  --floating-chatbot-left: 0px;
  --floating-chatbot-bottom: 0px;
  --floating-chatbot-panel-width: 380px;
  --floating-chatbot-panel-height: 560px;
  --floating-chatbot-panel-left: 0px;
  --floating-chatbot-panel-bottom: 68px;
  position: relative;
  left: var(--floating-chatbot-left);
  bottom: var(--floating-chatbot-bottom);
  display: flex;
  width: 56px;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  pointer-events: none;
}

.floating-chatbot--maximized {
  left: -24px;
  bottom: -24px;
  width: 100vw;
}

.floating-chatbot__panel {
  position: absolute;
  left: var(--floating-chatbot-panel-left);
  bottom: var(--floating-chatbot-panel-bottom);
  width: var(--floating-chatbot-panel-width);
  height: var(--floating-chatbot-panel-height);
  overflow: hidden;
  border: 1px solid rgba(91, 111, 170, 0.18);
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 24px 70px rgba(47, 60, 96, 0.22);
  opacity: 0;
  transform: translateY(16px) scale(0.98);
  transform-origin: bottom left;
  transition:
    opacity 0.18s ease,
    transform 0.18s ease,
    visibility 0.18s ease;
  visibility: hidden;
  pointer-events: none;
}

.floating-chatbot--maximized .floating-chatbot__panel {
  left: 0;
  bottom: 0;
  width: 100vw;
  height: 100vh;
  border-radius: 0;
}

.floating-chatbot--open .floating-chatbot__panel {
  opacity: 1;
  transform: translateY(0) scale(1);
  visibility: visible;
  pointer-events: auto;
}

.floating-chatbot__panel .ChatApp,
.floating-chatbot__panel .ChatFooter {
  background: #f8fafc;
}

.floating-chatbot--responding .floating-chatbot__panel .Composer {
  opacity: 0.72;
}

.floating-chatbot--responding .floating-chatbot__panel .Composer textarea,
.floating-chatbot--responding .floating-chatbot__panel .Composer input {
  cursor: not-allowed;
}

.floating-chatbot--responding .floating-chatbot__panel .Composer .SendBtn,
.floating-chatbot--responding .floating-chatbot__panel .Composer .Composer-sendBtn {
  opacity: 0.44;
  pointer-events: none;
}

.floating-chatbot__panel .Navbar {
  background: #5867d8;
  color: #ffffff;
}

.floating-chatbot__panel .Navbar-rightSlot {
  display: inline-flex;
  align-items: center;
}

.floating-chatbot__expand {
  display: inline-grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
  cursor: pointer;
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    transform 0.16s ease;
}

.floating-chatbot__resize {
  position: absolute;
  z-index: 12;
  border: 0;
  background: transparent;
  opacity: 0;
  transition:
    background 0.16s ease,
    opacity 0.16s ease;
}

.floating-chatbot--maximized .floating-chatbot__resize {
  display: none;
}

.floating-chatbot--maximized .floating-chatbot__toggle {
  display: none;
}

.floating-chatbot__resize--n,
.floating-chatbot__resize--s {
  left: 18px;
  right: 18px;
  height: 10px;
  cursor: ns-resize;
}

.floating-chatbot__resize--n {
  top: -3px;
}

.floating-chatbot__resize--s {
  bottom: -3px;
}

.floating-chatbot__resize--e,
.floating-chatbot__resize--w {
  top: 18px;
  bottom: 18px;
  width: 10px;
  cursor: ew-resize;
}

.floating-chatbot__resize--e {
  right: -3px;
}

.floating-chatbot__resize--w {
  left: -3px;
}

.floating-chatbot__resize--ne,
.floating-chatbot__resize--nw,
.floating-chatbot__resize--se,
.floating-chatbot__resize--sw {
  width: 22px;
  height: 22px;
  opacity: 0.72;
}

.floating-chatbot__resize--ne,
.floating-chatbot__resize--sw {
  cursor: nesw-resize;
}

.floating-chatbot__resize--nw,
.floating-chatbot__resize--se {
  cursor: nwse-resize;
}

.floating-chatbot__resize--ne {
  top: -3px;
  right: -3px;
}

.floating-chatbot__resize--nw {
  top: -3px;
  left: -3px;
}

.floating-chatbot__resize--se {
  right: 5px;
  bottom: 5px;
}

.floating-chatbot__resize--sw {
  left: -3px;
  bottom: -3px;
}

.floating-chatbot__resize--ne::before,
.floating-chatbot__resize--nw::before,
.floating-chatbot__resize--se::before,
.floating-chatbot__resize--sw::before {
  content: "";
  position: absolute;
  width: 12px;
  height: 12px;
  border-right: 2px solid rgba(88, 103, 216, 0.72);
  border-bottom: 2px solid rgba(88, 103, 216, 0.72);
  box-shadow:
    4px 4px 0 -2px rgba(88, 103, 216, 0.45),
    8px 8px 0 -4px rgba(88, 103, 216, 0.28);
}

.floating-chatbot__resize--ne::before {
  right: 5px;
  top: 5px;
  transform: rotate(-90deg);
}

.floating-chatbot__resize--nw::before {
  left: 5px;
  top: 5px;
  transform: rotate(180deg);
}

.floating-chatbot__resize--se::before {
  right: 5px;
  bottom: 5px;
}

.floating-chatbot__resize--sw::before {
  left: 5px;
  bottom: 5px;
  transform: rotate(90deg);
}

.floating-chatbot__resize:hover,
.floating-chatbot__resize:focus-visible {
  background: rgba(88, 103, 216, 0.1);
  opacity: 1;
  outline: none;
}

.floating-chatbot__resize--n:hover,
.floating-chatbot__resize--n:focus-visible,
.floating-chatbot__resize--s:hover,
.floating-chatbot__resize--s:focus-visible {
  background: linear-gradient(90deg, transparent, rgba(88, 103, 216, 0.22), transparent);
}

.floating-chatbot__resize--e:hover,
.floating-chatbot__resize--e:focus-visible,
.floating-chatbot__resize--w:hover,
.floating-chatbot__resize--w:focus-visible {
  background: linear-gradient(180deg, transparent, rgba(88, 103, 216, 0.22), transparent);
}

.floating-chatbot-resizing {
  user-select: none;
}

.floating-chatbot-dragging {
  user-select: none;
}

.floating-chatbot__expand:hover {
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(255, 255, 255, 0.42);
  transform: translateY(-1px);
}

.floating-chatbot__expand:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.75);
  outline-offset: 2px;
}

.floating-chatbot__panel .MessageContainer {
  background: linear-gradient(180deg, #f8fafc 0%, #eef3f8 100%);
}

.floating-chatbot__panel .Bubble {
  border-radius: 8px;
}

.floating-chatbot__panel .Bubble.text {
  line-height: 1.65;
}

.floating-chatbot__message {
  max-width: 100%;
}

.floating-chatbot__message--report {
  width: min(100%, calc(var(--floating-chatbot-width) - 72px));
}

.floating-chatbot--maximized .floating-chatbot__message--report {
  width: min(100%, 820px);
}

.floating-chatbot__markdown {
  width: min(330px, calc(100vw - 88px));
  box-sizing: border-box;
  border-radius: 8px;
  background: #ffffff;
  color: #263244;
  padding: 10px 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.floating-chatbot__message--report .floating-chatbot__markdown {
  width: 100%;
  border: 1px solid rgba(88, 103, 216, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 255, 0.98)),
    #ffffff;
  padding: 18px 20px;
  color: #1f2a44;
  font-size: 14px;
  line-height: 1.85;
  box-shadow: 0 12px 28px rgba(62, 78, 160, 0.08);
}

.floating-chatbot__markdown h1,
.floating-chatbot__markdown h2,
.floating-chatbot__markdown h3 {
  margin: 12px 0 6px;
  color: #1f2a44;
  font-size: 15px;
  line-height: 1.45;
}

.floating-chatbot__message--report .floating-chatbot__markdown h1 {
  margin: 0 0 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(88, 103, 216, 0.16);
  color: #172554;
  font-size: 21px;
  line-height: 1.35;
}

.floating-chatbot__message--report .floating-chatbot__markdown h2 {
  margin: 20px 0 9px;
  padding-left: 10px;
  border-left: 4px solid #5867d8;
  color: #243b73;
  font-size: 17px;
}

.floating-chatbot__message--report .floating-chatbot__markdown h3 {
  margin: 16px 0 7px;
  color: #334f8d;
  font-size: 15px;
}

.floating-chatbot__markdown h1:first-child,
.floating-chatbot__markdown h2:first-child,
.floating-chatbot__markdown h3:first-child,
.floating-chatbot__markdown p:first-child {
  margin-top: 0;
}

.floating-chatbot__markdown p,
.floating-chatbot__markdown ul,
.floating-chatbot__markdown ol {
  margin: 7px 0;
}

.floating-chatbot__message--report .floating-chatbot__markdown p,
.floating-chatbot__message--report .floating-chatbot__markdown ul,
.floating-chatbot__message--report .floating-chatbot__markdown ol {
  margin: 9px 0;
}

.floating-chatbot__markdown ul,
.floating-chatbot__markdown ol {
  padding-left: 20px;
}

.floating-chatbot__message--report .floating-chatbot__markdown ul,
.floating-chatbot__message--report .floating-chatbot__markdown ol {
  padding-left: 24px;
}

.floating-chatbot__markdown li {
  margin: 3px 0;
}

.floating-chatbot__message--report .floating-chatbot__markdown li {
  margin: 5px 0;
}

.floating-chatbot__message--report .floating-chatbot__markdown strong {
  color: #172554;
  font-weight: 800;
}

.floating-chatbot__markdown a {
  color: #4451ba;
  font-weight: 700;
}

.floating-chatbot__markdown code {
  border-radius: 4px;
  background: #eef2ff;
  padding: 1px 4px;
  color: #374151;
  font-size: 12px;
}

.floating-chatbot__markdown blockquote {
  margin: 8px 0;
  border-left: 3px solid #8b98e8;
  padding-left: 10px;
  color: #64748b;
}

.floating-chatbot__message--report .floating-chatbot__markdown blockquote {
  margin: 12px 0;
  border-left-color: #5867d8;
  border-radius: 0 8px 8px 0;
  background: rgba(88, 103, 216, 0.06);
  padding: 10px 12px;
}

.floating-chatbot__message--report .floating-chatbot__markdown table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  overflow: hidden;
  border-radius: 8px;
  font-size: 13px;
}

.floating-chatbot__message--report .floating-chatbot__markdown th,
.floating-chatbot__message--report .floating-chatbot__markdown td {
  border: 1px solid rgba(88, 103, 216, 0.14);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}

.floating-chatbot__message--report .floating-chatbot__markdown th {
  background: rgba(88, 103, 216, 0.08);
  color: #243b73;
}

.floating-chatbot__research {
  margin-top: 8px;
  width: min(320px, calc(100vw - 88px));
  border: 1px solid rgba(88, 103, 216, 0.18);
  border-radius: 8px;
  background: #ffffff;
  color: #1f2937;
  font-size: 12px;
  line-height: 1.5;
  overflow: hidden;
}

.floating-chatbot__message--report .floating-chatbot__research {
  width: 100%;
}

.floating-chatbot__research-title {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(88, 103, 216, 0.12);
  background: #f5f7fb;
  color: #374151;
  font-weight: 700;
}

.floating-chatbot__research-step {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.floating-chatbot__research-step:last-child {
  border-bottom: none;
}

.floating-chatbot__research-step--failed {
  background: #fff7ed;
}

.floating-chatbot__research-step--running {
  background: #f8fafc;
}

.floating-chatbot__research-step--completed .floating-chatbot__research-status {
  background: #dcfce7;
  color: #166534;
}

.floating-chatbot__research-step--running .floating-chatbot__research-status {
  background: #e0f2fe;
  color: #075985;
}

.floating-chatbot__research-status {
  display: inline-grid;
  min-width: 28px;
  height: 22px;
  place-items: center;
  border-radius: 6px;
  background: #eef2ff;
  color: #4451ba;
  font-size: 10px;
  font-weight: 800;
}

.floating-chatbot__research-step--failed .floating-chatbot__research-status {
  background: #ffedd5;
  color: #c2410c;
}

.floating-chatbot__research-body {
  min-width: 0;
}

.floating-chatbot__research-step-title {
  color: #111827;
  font-weight: 700;
}

.floating-chatbot__research-query,
.floating-chatbot__research-summary {
  margin-top: 3px;
  color: #64748b;
  overflow-wrap: anywhere;
}

.floating-chatbot__toggle {
  position: relative;
  display: inline-grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border: none;
  border-radius: 50%;
  background: #5867d8;
  color: #ffffff;
  box-shadow: 0 16px 36px rgba(62, 78, 160, 0.34);
  cursor: pointer;
  pointer-events: auto;
  touch-action: none;
  transition:
    background 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.floating-chatbot__toggle:active {
  cursor: grabbing;
}

.floating-chatbot__toggle:hover {
  background: #4451ba;
  box-shadow: 0 18px 42px rgba(62, 78, 160, 0.4);
  transform: translateY(-2px);
}

.floating-chatbot--responding .floating-chatbot__toggle {
  animation: floating-chatbot-thinking-pulse 1.4s ease-in-out infinite;
  background: #4f5fd0;
  box-shadow:
    0 18px 42px rgba(62, 78, 160, 0.42),
    0 0 0 0 rgba(88, 103, 216, 0.3);
}

.floating-chatbot--responding .floating-chatbot__toggle::before {
  content: "";
  position: absolute;
  inset: 5px;
  border: 2px solid rgba(255, 255, 255, 0.28);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: floating-chatbot-thinking-spin 0.82s linear infinite;
}

.floating-chatbot--responding .floating-chatbot__toggle-mark {
  transform: scale(0.86);
}

.floating-chatbot__toggle:focus-visible {
  outline: 3px solid rgba(88, 103, 216, 0.28);
  outline-offset: 4px;
}

.floating-chatbot__toggle-mark {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0;
  transition: transform 0.18s ease;
}

@keyframes floating-chatbot-thinking-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes floating-chatbot-thinking-pulse {
  0%,
  100% {
    box-shadow:
      0 16px 36px rgba(62, 78, 160, 0.34),
      0 0 0 0 rgba(88, 103, 216, 0.26);
  }

  50% {
    box-shadow:
      0 20px 48px rgba(62, 78, 160, 0.46),
      0 0 0 9px rgba(88, 103, 216, 0);
  }
}

@media (max-width: 640px) {
  .floating-chatbot-host {
    left: 16px;
    right: 16px;
    bottom: 16px;
  }

  .floating-chatbot {
    width: 56px;
  }

  .floating-chatbot--maximized {
    left: -16px;
    bottom: -16px;
    width: 100vw;
  }

  .floating-chatbot--maximized .floating-chatbot__panel {
    height: 100vh;
  }
}
</style>
