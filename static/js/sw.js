// static/js/sw.js — Service Worker for Web Push notifications

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", function (event) {
  let data = { title: "ProManager", body: "You have a new notification." };
  if (event.data) {
    try { data = event.data.json(); } catch (_) {}
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/img/icon-192.png",
      badge: "/static/img/icon-192.png",
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      if (list.length > 0) return list[0].focus();
      return clients.openWindow("/notifications");
    })
  );
});

self.addEventListener("pushsubscriptionchange", function (event) {
  event.waitUntil(
    self.registration.pushManager.subscribe(event.oldSubscription.options)
      .then(sub => {
        const key = sub.getKey("p256dh");
        const auth = sub.getKey("auth");
        const body = new FormData();
        body.append("endpoint", sub.endpoint);
        body.append("p256dh", btoa(String.fromCharCode(...new Uint8Array(key))));
        body.append("auth", btoa(String.fromCharCode(...new Uint8Array(auth))));
        return fetch("/notifications/webpush/resubscribe", { method: "POST", body });
      })
  );
});
