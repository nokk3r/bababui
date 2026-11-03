import { createApp } from "vue";
import "./fonts.css";
import App from "./App.vue";
import "./app.css";
import { initI18n } from "./lib/i18n.js";
import { initTheme } from "./lib/theme.js";
import { boot } from "./store.js";

initTheme();
await initI18n();
createApp(App).mount("#app");
boot();
