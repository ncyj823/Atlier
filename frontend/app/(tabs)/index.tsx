import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, ScrollView, ActivityIndicator,
  KeyboardAvoidingView, Platform, RefreshControl,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { api, EventItem } from "@/src/api";
import { colors, spacing, MODES, modeColor, modeLabel } from "@/src/theme";
import { useVoiceCapture } from "@/src/use-voice";
import { scheduleEventReminders } from "@/src/notifications";

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
  const [parsing, setParsing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<any>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [remindersToast, setRemindersToast] = useState<string | null>(null);

  const voice = useVoiceCapture();

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

  const onMicPress = async () => {
    Haptics.selectionAsync();
    if (!voice.isRecording) {
      await voice.start();
    } else {
      const transcript = await voice.stopAndTranscribe();
      if (transcript) {
        setText((prev) => (prev ? prev + " " + transcript : transcript));
      }
    }
  };

  const onParse = async () => {
    if (!text.trim()) return;
    setParsing(true);
    setPreview(null);
    try {
      Haptics.selectionAsync();
      const data = await api.parse(text.trim());
      setPreview(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setParsing(false);
    }
  };

  const onConfirm = async () => {
    if (!preview) return;
    setCreating(true);
    try {
      const created = await api.createEvent({
        title: preview.title,
        mode: preview.mode,
        start_iso: preview.start_iso,
        duration_minutes: preview.duration_minutes,
        client_id: preview.client_id,
        client_email: preview.client_email,
        notes: preview.notes,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // Schedule local reminders (in-app)
      const ids = await scheduleEventReminders(created.title, created.start_iso);
      setRemindersToast(
        ids.length > 0 ? `${ids.length} reminder${ids.length > 1 ? "s" : ""} set on this device`
                       : "Reminders not set (notifications disabled)"
      );
      setTimeout(() => setRemindersToast(null), 3500);
      setText(""); setPreview(null);
      loadToday();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const today = new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.lg, paddingBottom: spacing.xxxl }]}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={loadToday} tintColor={colors.brand} />}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.kicker} testID="today-kicker">Atelier · Today</Text>
        <Text style={styles.h1} testID="today-date">{today}</Text>

        <View style={styles.composer} testID="schedule-composer">
          <View style={styles.composerHeader}>
            <Text style={styles.composerLabel}>{voice.isRecording ? "Listening…" : voice.transcribing ? "Transcribing…" : "Note to schedule"}</Text>
            <Pressable
              testID="mic-button"
              onPress={onMicPress}
              disabled={voice.transcribing}
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
          />
          {voice.error && <Text style={styles.errorText}>{voice.error}</Text>}
          <View style={styles.composerActions}>
            <Pressable
              testID="parse-button"
              onPress={onParse}
              disabled={!text.trim() || parsing}
              style={({ pressed }) => [
                styles.primaryBtn,
                (!text.trim() || parsing) && { opacity: 0.5 },
                pressed && { opacity: 0.85 },
              ]}
            >
              {parsing ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <>
                  <Feather name="zap" color={colors.onBrandPrimary} size={14} />
                  <Text style={styles.primaryBtnText}>Parse</Text>
                </>
              )}
            </Pressable>
          </View>
        </View>

        {preview && (
          <View style={styles.preview} testID="schedule-preview">
            <Text style={styles.previewKicker}>Preview · {modeLabel(preview.mode)}</Text>
            <Text style={styles.previewTitle}>{preview.title}</Text>
            <Text style={styles.previewMeta}>
              {new Date(preview.start_iso).toLocaleString([], {
                weekday: "long", day: "numeric", month: "short",
                hour: "numeric", minute: "2-digit",
              })}
            </Text>
            {preview.client_name && (
              <Text style={styles.previewMeta}>
                with {preview.client_name}{preview.client_id ? "  ·  linked" : "  ·  no matching client"}
              </Text>
            )}
            <View style={styles.previewActions}>
              <Pressable testID="confirm-event" onPress={onConfirm} disabled={creating} style={styles.primaryBtn}>
                {creating ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Confirm & set 3 reminders</Text>}
              </Pressable>
              <Pressable testID="cancel-preview" onPress={() => setPreview(null)} style={styles.ghostBtn}>
                <Text style={styles.ghostBtnText}>Discard</Text>
              </Pressable>
            </View>
          </View>
        )}

        {remindersToast && (
          <View style={styles.toast} testID="reminders-toast">
            <Feather name="bell" color={colors.brand} size={14} />
            <Text style={styles.toastText}>{remindersToast}</Text>
          </View>
        )}

        <Text style={styles.sectionTitle}>Today's agenda</Text>
        {loading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.lg }} />
        ) : events.length === 0 ? (
          <View style={styles.empty}>
            <Feather name="feather" size={28} color={colors.onSurfaceTertiary} />
            <Text style={styles.emptyText}>Nothing scheduled. The day is yours.</Text>
          </View>
        ) : (
          events.map((ev) => (
            <View key={ev.id} style={styles.eventRow} testID={`event-row-${ev.id}`}>
              <View style={[styles.eventBar, { backgroundColor: modeColor(ev.mode) }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.eventTime}>{fmtTime(ev.start_iso)}  ·  {ev.duration_minutes}m</Text>
                <Text style={styles.eventTitle}>{ev.title}</Text>
                <Text style={styles.eventMeta}>
                  {modeLabel(ev.mode)}{ev.client_name ? `  ·  ${ev.client_name}` : ""}
                </Text>
                {ev.meet_link ? (
                  <Text style={styles.eventLink} numberOfLines={1}>{ev.meet_link}</Text>
                ) : null}
              </View>
            </View>
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
  composerLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
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
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12 },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },

  preview: { backgroundColor: colors.surfaceSecondary, padding: spacing.lg, gap: 6 },
  previewKicker: { letterSpacing: 2, textTransform: "uppercase", fontSize: 10, color: colors.brand, marginBottom: 4 },
  previewTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface },
  previewMeta: { color: colors.onSurfaceSecondary, fontSize: 14 },
  previewActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },

  toast: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.brandSecondary,
  },
  toastText: { color: colors.onBrandTertiary, fontSize: 13 },

  sectionTitle: {
    fontFamily: "Georgia", fontSize: 20, color: colors.onSurface,
    marginTop: spacing.lg, marginBottom: spacing.sm,
  },

  empty: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.sm },
  emptyText: { color: colors.onSurfaceTertiary, fontStyle: "italic" },

  eventRow: {
    flexDirection: "row", gap: spacing.md, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  eventBar: { width: 3, alignSelf: "stretch" },
  eventTime: { color: colors.onSurfaceTertiary, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  eventTitle: { fontFamily: "Georgia", fontSize: 18, color: colors.onSurface, marginTop: 2 },
  eventMeta: { color: colors.onSurfaceSecondary, fontSize: 13, marginTop: 2 },
  eventLink: { color: colors.brand, fontSize: 12, marginTop: 4 },

  errorText: { color: colors.error, marginTop: spacing.sm, fontSize: 13 },

  helperHeader: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, marginTop: spacing.xl },
  modesLegend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  modeChipLegend: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  modeChipText: { fontSize: 12, color: colors.onSurfaceSecondary },
});
