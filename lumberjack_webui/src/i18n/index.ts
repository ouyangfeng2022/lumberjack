import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./locales/en";
import zh from "./locales/zh";
import { workspaceEn, workspaceZh } from "./workspace";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: { ...en, ...workspaceEn } },
      zh: { translation: { ...zh, ...workspaceZh } },
    },
    fallbackLng: "en",
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "lumberjack_lang",
      caches: ["localStorage"],
    },
  });

export default i18n;
