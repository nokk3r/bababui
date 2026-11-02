import { createApp } from "vue";
import App from "./App.vue";
import "./app.css";
import { initI18n } from "./lib/i18n.js";
import { boot } from "./store.js";

await initI18n();
createApp(App).mount("#app");
boot();
