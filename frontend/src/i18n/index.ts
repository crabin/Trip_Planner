import { createI18n } from "vue-i18n";

import { messages } from "./messages";

export const SUPPORTED_LOCALES = ["zh-CN", "en-US"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "zh-CN";
export const LOCALE_STORAGE_KEY = "trip_planner.locale";

export function isSupportedLocale(value: string | null): value is Locale {
  return SUPPORTED_LOCALES.includes(value as Locale);
}

export function getStoredLocale(): Locale {
  if (typeof window === "undefined") {
    return DEFAULT_LOCALE;
  }

  const storedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  return isSupportedLocale(storedLocale) ? storedLocale : DEFAULT_LOCALE;
}

export const i18n = createI18n({
  legacy: false,
  locale: getStoredLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages,
});
