"use client";
import { useEffect } from "react";

/** Registers the service worker that makes EduCrew installable. Browsers only allow this on
 * https or localhost; on plain http over Wi-Fi it silently does nothing (the app still works). */
export function RegisterServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);
  return null;
}
