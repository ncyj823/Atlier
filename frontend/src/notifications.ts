import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

let configured = false;

async function ensureSetup() {
  if (configured) return;
  configured = true;
  if (Platform.OS === "android") {
    try {
      await Notifications.setNotificationChannelAsync("atelier-reminders", {
        name: "Atelier Reminders",
        importance: Notifications.AndroidImportance.HIGH,
        sound: "default",
      });
    } catch {}
  }
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

export async function ensureNotifPermission(): Promise<boolean> {
  await ensureSetup();
  if (Platform.OS === "web") return false;
  const cur = await Notifications.getPermissionsAsync();
  if (cur.granted) return true;
  if (!cur.canAskAgain) return false;
  const req = await Notifications.requestPermissionsAsync({
    ios: { allowAlert: true, allowBadge: false, allowSound: true },
  });
  return !!req.granted;
}

export async function scheduleEventReminders(
  eventTitle: string,
  startIso: string,
): Promise<string[]> {
  const granted = await ensureNotifPermission();
  if (!granted) return [];
  const start = new Date(startIso);
  const now = Date.now();
  const offsets = [
    { ms: 24 * 60 * 60 * 1000, label: "Tomorrow" },
    { ms: 60 * 60 * 1000, label: "In 1 hour" },
    { ms: 15 * 60 * 1000, label: "In 15 minutes" },
  ];
  const ids: string[] = [];
  for (const o of offsets) {
    const triggerAt = start.getTime() - o.ms;
    if (triggerAt <= now + 5_000) continue; // skip past-due
    try {
      const id = await Notifications.scheduleNotificationAsync({
        content: {
          title: `${o.label}: ${eventTitle}`,
          body: `Starts at ${start.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`,
          sound: "default",
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DATE,
          date: new Date(triggerAt),
          channelId: "atelier-reminders",
        } as any,
      });
      ids.push(id);
    } catch (e) {
      console.warn("schedule failed", e);
    }
  }
  return ids;
}

export async function cancelReminders(ids: string[]) {
  for (const id of ids) {
    try { await Notifications.cancelScheduledNotificationAsync(id); } catch {}
  }
}
