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
}

.floating-chatbot {
  display: flex;
  width: min(380px, calc(100vw - 32px));
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  pointer-events: none;
}

.floating-chatbot__panel {
  width: 100%;
  height: min(560px, calc(100vh - 120px));
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

.floating-chatbot__panel .Navbar {
  background: #5867d8;
  color: #ffffff;
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

.floating-chatbot__toggle {
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
  transition:
    background 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.floating-chatbot__toggle:hover {
  background: #4451ba;
  box-shadow: 0 18px 42px rgba(62, 78, 160, 0.4);
  transform: translateY(-2px);
}

.floating-chatbot__toggle:focus-visible {
  outline: 3px solid rgba(88, 103, 216, 0.28);
  outline-offset: 4px;
}

.floating-chatbot__toggle-mark {
  font-size: 16px;
  font-weight: 800;
  letter-spacing: 0;
}

@media (max-width: 640px) {
  .floating-chatbot-host {
    left: 16px;
    right: 16px;
    bottom: 16px;
  }

  .floating-chatbot {
    width: 100%;
  }

  .floating-chatbot__panel {
    height: min(520px, calc(100vh - 96px));
  }
}
</style>
