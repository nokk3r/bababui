import { ref } from "vue";
import { t, tMsg } from "./i18n.js";

export const loginOpen = ref(false);

export function authHeaders() {
  const headers = {};
  const token = sessionStorage.getItem("token");
  if (token) headers.Authorization = `Bearer ${encodeURIComponent(token)}`;
  return headers;
}

export async function api(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  const request = { ...options, headers };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(options.json);
  }
  const response = await fetch(path, request);
  if (response.status === 401) {
    loginOpen.value = true;
    const error = new Error("unauthorized");
    error.unauthorized = true;
    throw error;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      /* тело не JSON */
    }
    if (detail && typeof detail !== "string") detail = JSON.stringify(detail);
    throw new Error(tMsg(detail) || t("error.requestFailed"));
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response.text();
}
