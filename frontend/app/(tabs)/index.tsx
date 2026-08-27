import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform, RefreshControl, Modal,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { api, EventItem } from "@/src/api";
import { colors, spacing, MODES, modeColor, modeLabel } from "@/src/theme";
import { useVoiceCapture } from "@/src/use-voice";
import { scheduleEventReminders } from "@/src/notifications";

// Threshold: 4 or more meetings = heavy / overloaded day
const OVERLOAD_THRESHOLD = 4;

function todayBounds() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0).toISOString();
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59).toISOString();
  return { start, end };
}

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch { return iso; }
}

export default function TodayScreen() {
  const insets = useSafeAreaInsets();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Reschedule sheet
  const [rescheduleEvent, setRescheduleEvent] = useState<EventItem | null>(null);
  const [rescheduling, setRescheduling] = useState(false);

  const loadToday = useCallback(async () => {
    try {
      setError(null);
      const { start, end } = todayBounds();
      const data = await api.listEvents(start, end);
      setEvents(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { loadToday(); }, [loadToday]));

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const sendNow = useCallback(async (raw: string) => {
    const value = raw.trim();
    if (!value) return;
    setSending(true);
    setError(null);
    try {
      Haptics.selectionAsync();
      const parsed = await api.parse(value);
      const created = await api.createEvent({
        title: parsed.title,
        mode: parsed.mode,
        start_iso: parsed.start_iso,
        duration_minutes: parsed.duration_minutes,
        client_id: parsed.client_id,
        client_email: parsed.client_email,
        notes: parsed.notes,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const ids = await scheduleEventReminders(created.title, created.start_iso);
      showToast(
        ids.length > 0
          ? `Scheduled · ${ids.length} reminder${ids.length > 1 ? "s" : ""} on this device`
          : `Scheduled · ${created.title}`
      );
      setText("");
      loadToday();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSending(false);
    }
  }, [loadToday]);

  const voice = useVoiceCapture({
    onAutoStop: (transcript) => {
      // End-of-sentence detected → fire send immediately
      if (transcript) {
        Haptics.selectionAsync();
        sendNow(transcript);
      }
    },
  });

  const onMicPress = async () => {
    Haptics.selectionAsync();
    if (!voice.isRecording) {
      await voice.start();
    } else {
      // Manual stop fallback: insert text in field (don't auto-send)
      const transcript = await voice.stopAndTranscribe();
      if (transcript) setText((prev) => (prev ? prev + " " + transcript : transcript));
    }
  };

  const onSend = () => sendNow(text);

  const onReschedule = async (offset: "1h" | "1d" | "1w" | "next-morning") => {
    if (!rescheduleEvent) return;
    setRescheduling(true);
    try {
      const dt = new Date(rescheduleEvent.start_iso);
      if (offset === "1h") dt.setHours(dt.getHours() + 1);
      if (offset === "1d") dt.setDate(dt.getDate() + 1);
      if (offset === "1w") dt.setDate(dt.getDate() + 7);
      if (offset === "next-morning") {
        dt.setDate(dt.getDate() + 1);
        dt.setHours(10, 0, 0, 0);
      }
      const updated = await api.rescheduleEvent(rescheduleEvent.id, dt.toISOString());
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      await scheduleEventReminders(updated.title, updated.start_iso);
      showToast(`Moved to ${dt.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}`);
      setRescheduleEvent(null);
      loadToday();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRescheduling(false);
    }
  };

  const today = new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
  const overloaded = events.length >= OVERLOAD_THRESHOLD;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface, overflow: "hidden" }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg, paddingBottom: spacing.xxxl }]}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={loadToday} tintColor={colors.brand} />}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.kicker} testID="today-kicker">Atelier · Today</Text>
        <Text style={styles.h1} testID="today-date">{today}</Text>

        <View style={styles.composer} testID="schedule-composer">
          <View style={styles.composerHeader}>
            <Text style={styles.composerLabel}>
              {voice.isRecording ? "Listening…  (auto-stops on silence)" : voice.transcribing ? "Transcribing…" : "Note to schedule"}
            </Text>
            <Pressable
              testID="mic-button"
              onPress={onMicPress}
              disabled={voice.transcribing || sending}
              style={[styles.micBtn, voice.isRecording && styles.micBtnActive]}
            >
              {voice.transcribing ? (
                <ActivityIndicator color={colors.brand} />
              ) : (
                <Feather
                  name={voice.isRecording ? "square" : "mic"}
                  color={voice.isRecording ? "#fff" : colors.brand}
                  size={16}
                />
              )}
            </Pressable>
          </View>
          <TextInput
            testID="schedule-input"
            value={text}
            onChangeText={setText}
            placeholder={'Tap the mic, or type "Schedule a design call for Anaïs at 6pm IST on coming Wednesday"'}
            placeholderTextColor={colors.onSurfaceTertiary}
            multiline
            style={styles.composerInput}
            returnKeyType="send"
            onSubmitEditing={onSend}
          />
          {voice.error && <Text style={styles.errorText}>{voice.error}</Text>}
          <View style={styles.composerActions}>
            <Pressable
              testID="send-button"
              onPress={onSend}
              disabled={!text.trim() || sending}
              style={({ pressed }) => [
                styles.primaryBtn,
                (!text.trim() || sending) && { opacity: 0.5 },
                pressed && { opacity: 0.85 },
              ]}
            >
              {sending ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <>
                  <Feather name="send" color={colors.onBrandPrimary} size={14} />
                  <Text style={styles.primaryBtnText}>Send</Text>
                </>
              )}
            </Pressable>
          </View>
        </View>

        {toast && (
          <View style={styles.toast} testID="reminders-toast">
            <Feather name="check-circle" color={colors.brand} size={14} />
            <Text style={styles.toastText}>{toast}</Text>
          </View>
        )}

        <View style={styles.agendaHeader}>
          <Text style={styles.sectionTitle}>Today's agenda</Text>
          {events.length > 0 && (
            <Text style={[styles.count, overloaded && styles.countRed]} testID="agenda-count">
              {events.length} meeting{events.length === 1 ? "" : "s"}
            </Text>
          )}
        </View>

        {overloaded && (
          <View style={styles.overloadBanner} testID="overload-banner">
            <Feather name="alert-triangle" color={colors.onError} size={18} />
            <Text style={styles.overloadText}>
              Heavy day — {events.length} meetings. Tap any event below to reschedule.
            </Text>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.lg }} />
        ) : events.length === 0 ? (
          <View style={styles.empty}>
            <Feather name="feather" size={28} color={colors.onSurfaceTertiary} />
            <Text style={styles.emptyText}>Nothing scheduled. The day is yours.</Text>
          </View>
        ) : (
          events.map((ev) => (
            <Pressable
              key={ev.id}
              testID={`event-row-${ev.id}`}
              onPress={() => setRescheduleEvent(ev)}
              style={[styles.eventRow, overloaded && styles.eventRowOverload]}
            >
              <View style={[styles.eventBar, { backgroundColor: overloaded ? colors.error : modeColor(ev.mode) }]} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.eventTime, overloaded && { color: colors.error }]}>
                  {fmtTime(ev.start_iso)}  ·  {ev.duration_minutes}m
                </Text>
                <Text style={styles.eventTitle}>{ev.title}</Text>
                <Text style={styles.eventMeta}>
                  {modeLabel(ev.mode)}{ev.client_name ? `  ·  ${ev.client_name}` : ""}
                </Text>
                {ev.meet_link ? (
                  <Text style={styles.eventLink} numberOfLines={1}>{ev.meet_link}</Text>
                ) : null}
              </View>
              <View style={styles.rescheduleHint}>
                <Feather name="refresh-cw" color={overloaded ? colors.error : colors.onSurfaceTertiary} size={14} />
                <Text style={[styles.rescheduleHintText, overloaded && { color: colors.error }]}>Reschedule</Text>
              </View>
            </Pressable>
          ))
        )}

        {error && <Text style={styles.errorText} testID="error-text">{error}</Text>}

        <Text style={styles.helperHeader}>Modes</Text>
        <View style={styles.modesLegend}>
          {MODES.map((m) => (
            <View key={m.key} style={styles.modeChipLegend}>
              <View style={[styles.dot, { backgroundColor: m.color }]} />
              <Text style={styles.modeChipText}>{m.label}</Text>
            </View>
          ))}
        </View>
      </ScrollView>

      <Modal
        visible={!!rescheduleEvent}
        transparent
        animationType="slide"
        onRequestClose={() => setRescheduleEvent(null)}
      >
        <Pressable style={styles.backdrop} onPress={() => setRescheduleEvent(null)} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]} testID="reschedule-sheet">
          <Text style={styles.kicker}>Reschedule</Text>
          <Text style={styles.sheetTitle}>{rescheduleEvent?.title}</Text>
          <Text style={styles.sheetMeta}>
            Currently {rescheduleEvent ? new Date(rescheduleEvent.start_iso).toLocaleString([], {
              weekday: "long", day: "numeric", month: "short",
              hour: "numeric", minute: "2-digit",
            }) : ""}
          </Text>
          <View style={styles.optionsRow}>
            <Pressable testID="reschedule-1h" onPress={() => onReschedule("1h")} disabled={rescheduling} style={styles.optionBtn}>
              <Text style={styles.optionBtnLabel}>+1 hour</Text>
            </Pressable>
            <Pressable testID="reschedule-1d" onPress={() => onReschedule("1d")} disabled={rescheduling} style={styles.optionBtn}>
              <Text style={styles.optionBtnLabel}>+1 day</Text>
            </Pressable>
            <Pressable testID="reschedule-1w" onPress={() => onReschedule("1w")} disabled={rescheduling} style={styles.optionBtn}>
              <Text style={styles.optionBtnLabel}>+1 week</Text>
            </Pressable>
            <Pressable testID="reschedule-next-morning" onPress={() => onReschedule("next-morning")} disabled={rescheduling} style={[styles.optionBtn, styles.optionBtnPrimary]}>
              <Text style={[styles.optionBtnLabel, { color: "#fff" }]}>Tomorrow 10 AM</Text>
            </Pressable>
          </View>
          {rescheduling && <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.md }} />}
          <Pressable testID="reschedule-cancel" onPress={() => setRescheduleEvent(null)} style={styles.ghostBtn}>
            <Text style={styles.ghostBtnText}>Cancel</Text>
          </Pressable>
        </View>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: spacing.xl, gap: spacing.lg },
  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  h1: { fontFamily: "Georgia", fontSize: 32, color: colors.onSurface, lineHeight: 38, marginBottom: spacing.lg },

  composer: {
    backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.borderStrong, padding: spacing.lg, gap: spacing.md,
  },
  composerHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  composerLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, flex: 1, marginRight: spacing.sm },
  composerInput: {
    fontFamily: "Georgia", fontSize: 18, lineHeight: 26, color: colors.onSurface,
    minHeight: 80, textAlignVertical: "top",
  },
  composerActions: { flexDirection: "row", justifyContent: "flex-end" },
  micBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.borderStrong, borderRadius: 20,
  },
  micBtnActive: { backgroundColor: colors.brand, borderColor: colors.brand },

  primaryBtn: {
    backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12,
    flexDirection: "row", alignItems: "center", gap: 6,
  },
  primaryBtnText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12, alignSelf: "flex-start" },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },

  toast: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.brandSecondary,
  },
  toastText: { color: colors.onBrandTertiary, fontSize: 13 },

  agendaHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginTop: spacing.lg },
  sectionTitle: { fontFamily: "Georgia", fontSize: 20, color: colors.onSurface },
  count: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  countRed: { color: colors.error },

  overloadBanner: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.error, paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  overloadText: { color: colors.onError, fontSize: 13, flex: 1, lineHeight: 18 },

  empty: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.sm },
  emptyText: { color: colors.onSurfaceTertiary, fontStyle: "italic" },

  eventRow: {
    flexDirection: "row", gap: spacing.md, paddingVertical: spacing.md, alignItems: "center",
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  eventRowOverload: { borderBottomColor: colors.error },
  eventBar: { width: 3, alignSelf: "stretch" },
  eventTime: { color: colors.onSurfaceTertiary, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  eventTitle: { fontFamily: "Georgia", fontSize: 18, color: colors.onSurface, marginTop: 2 },
  eventMeta: { color: colors.onSurfaceSecondary, fontSize: 13, marginTop: 2 },
  eventLink: { color: colors.brand, fontSize: 12, marginTop: 4 },
  rescheduleHint: { alignItems: "center", gap: 2, paddingHorizontal: spacing.sm },
  rescheduleHintText: { fontSize: 9, letterSpacing: 1.2, textTransform: "uppercase", color: colors.onSurfaceTertiary },

  errorText: { color: colors.error, marginTop: spacing.sm, fontSize: 13 },

  helperHeader: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, marginTop: spacing.xl },
  modesLegend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  modeChipLegend: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  modeChipText: { fontSize: 12, color: colors.onSurfaceSecondary },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,25,24,0.4)" },
  sheet: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: colors.surface, padding: spacing.xl, gap: spacing.sm,
    borderTopWidth: 1, borderColor: colors.borderStrong,
  },
  sheetTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface, marginTop: 4 },
  sheetMeta: { color: colors.onSurfaceSecondary, fontSize: 13, marginBottom: spacing.md },
  optionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  optionBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderWidth: 1, borderColor: colors.borderStrong,
  },
  optionBtnPrimary: { backgroundColor: colors.brand, borderColor: colors.brand },
  optionBtnLabel: { color: colors.onSurface, fontSize: 13, letterSpacing: 0.8, textTransform: "uppercase" },
});
