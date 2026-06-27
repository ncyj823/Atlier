import { useCallback, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Dimensions } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api, EventItem } from "@/src/api";
import { colors, spacing, MODES, modeColor, modeLabel } from "@/src/theme";

const DAY_LABELS = ["S", "M", "T", "W", "T", "F", "S"];

function monthGrid(year: number, month: number) {
  const first = new Date(year, month, 1);
  const startWeekday = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: ({ d: number; iso: string } | null)[] = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const dt = new Date(year, month, d);
    cells.push({ d, iso: dt.toISOString().slice(0, 10) });
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export default function CalendarScreen() {
  const insets = useSafeAreaInsets();
  const today = new Date();
  const [cursor, setCursor] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const [activeModes, setActiveModes] = useState<Record<string, boolean>>({
    design_call: true, measurement_call: true, sending_pieces: true, personal: true,
  });
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selected, setSelected] = useState<string>(today.toISOString().slice(0, 10));
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const y = cursor.getFullYear(), m = cursor.getMonth();
      const start = new Date(y, m, 1).toISOString();
      const end = new Date(y, m + 1, 0, 23, 59, 59).toISOString();
      const data = await api.listEvents(start, end);
      setEvents(data);
    } finally {
      setLoading(false);
    }
  }, [cursor]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const cells = useMemo(() => monthGrid(cursor.getFullYear(), cursor.getMonth()), [cursor]);

  const eventsByDay = useMemo(() => {
    const map: Record<string, EventItem[]> = {};
    for (const ev of events) {
      if (!activeModes[ev.mode]) continue;
      const day = ev.start_iso.slice(0, 10);
      (map[day] ||= []).push(ev);
    }
    return map;
  }, [events, activeModes]);

  const dayEvents = (eventsByDay[selected] || []).sort((a, b) => a.start_iso.localeCompare(b.start_iso));

  const monthLabel = cursor.toLocaleDateString([], { month: "long", year: "numeric" });
  const todayIso = new Date().toISOString().slice(0, 10);

  // Cell sizing — generous so each day feels like a tile
  const screenW = Dimensions.get("window").width;
  const cellSize = Math.floor((screenW - spacing.xl * 2) / 7);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingBottom: insets.bottom + 100 }}
      stickyHeaderIndices={[0]}
    >
      <View style={[styles.stickyHeader, { paddingTop: insets.top + spacing.lg }]}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.kicker}>Atelier · Calendar</Text>
            <Text style={styles.h1} testID="calendar-month">{monthLabel}</Text>
          </View>
          <View style={styles.navRow}>
            <Pressable
              testID="prev-month"
              onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
              style={styles.navBtn}
            >
              <Feather name="chevron-left" color={colors.onSurface} size={22} />
            </Pressable>
            <Pressable
              testID="today-btn"
              onPress={() => {
                const n = new Date();
                setCursor(new Date(n.getFullYear(), n.getMonth(), 1));
                setSelected(n.toISOString().slice(0, 10));
              }}
              style={styles.navBtn}
            >
              <Text style={styles.navBtnText}>Today</Text>
            </Pressable>
            <Pressable
              testID="next-month"
              onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
              style={styles.navBtn}
            >
              <Feather name="chevron-right" color={colors.onSurface} size={22} />
            </Pressable>
          </View>
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.modeRow}
        >
          {MODES.map((m) => {
            const on = activeModes[m.key];
            return (
              <Pressable
                key={m.key}
                testID={`mode-toggle-${m.key}`}
                onPress={() => setActiveModes((s) => ({ ...s, [m.key]: !s[m.key] }))}
                style={[styles.modeChip, { borderColor: on ? m.color : colors.border }, on && { backgroundColor: m.color }]}
              >
                <View style={[styles.modeDot, { backgroundColor: on ? "#fff" : m.color }]} />
                <Text style={[styles.modeChipText, { color: on ? "#fff" : colors.onSurface }]}>{m.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <View style={styles.weekRow}>
        {DAY_LABELS.map((d, i) => <Text key={i} style={styles.weekLabel}>{d}</Text>)}
      </View>

      <View style={styles.grid}>
        {cells.map((c, i) => {
          if (!c) return <View key={i} style={[styles.cell, { width: cellSize, height: cellSize + 16 }]} />;
          const evs = eventsByDay[c.iso] || [];
          const isToday = c.iso === todayIso;
          const isSel = c.iso === selected;
          return (
            <Pressable
              key={i}
              testID={`day-${c.iso}`}
              onPress={() => setSelected(c.iso)}
              style={[
                styles.cell,
                { width: cellSize, height: cellSize + 16 },
                isSel && styles.cellSelected,
                isToday && !isSel && styles.cellToday,
              ]}
            >
              <Text style={[
                styles.cellNum,
                isToday && { color: colors.brand },
                isSel && { color: "#fff" },
              ]}>{c.d}</Text>
              <View style={styles.barsCol}>
                {evs.slice(0, 4).map((ev) => (
                  <View
                    key={ev.id}
                    style={[styles.eventLine, { backgroundColor: isSel ? "#fff" : modeColor(ev.mode) }]}
                  />
                ))}
                {evs.length > 4 ? (
                  <Text style={[styles.moreText, isSel && { color: "#fff" }]}>+{evs.length - 4}</Text>
                ) : null}
              </View>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.detailHeader}>
        <Text style={styles.sectionTitle}>
          {new Date(selected + "T00:00:00").toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })}
        </Text>
        {loading && <ActivityIndicator color={colors.brand} />}
      </View>

      <View style={{ paddingHorizontal: spacing.xl }}>
        {dayEvents.length === 0 ? (
          <Text style={styles.empty} testID="day-empty">No events on this day.</Text>
        ) : (
          dayEvents.map((ev) => (
            <View key={ev.id} style={styles.eventRow} testID={`cal-event-${ev.id}`}>
              <View style={[styles.eventBar, { backgroundColor: modeColor(ev.mode) }]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.eventTime}>
                  {new Date(ev.start_iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                  {"  ·  "}{modeLabel(ev.mode)}
                </Text>
                <Text style={styles.eventTitle}>{ev.title}</Text>
                {ev.client_name ? <Text style={styles.eventMeta}>with {ev.client_name}</Text> : null}
              </View>
            </View>
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  stickyHeader: { backgroundColor: colors.surface, paddingHorizontal: spacing.xl, paddingBottom: spacing.sm, borderBottomWidth: 1, borderColor: colors.border },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" },
  navRow: { flexDirection: "row", gap: spacing.xs },
  navBtn: { paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  navBtnText: { fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", color: colors.onSurface },

  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  h1: { fontFamily: "Georgia", fontSize: 28, color: colors.onSurface, marginTop: 4 },

  modeRow: { gap: spacing.sm, paddingTop: spacing.md, paddingRight: spacing.lg },
  modeChip: {
    flexShrink: 0, height: 36, paddingHorizontal: 14,
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderRadius: 999,
  },
  modeDot: { width: 6, height: 6, borderRadius: 3 },
  modeChipText: { fontSize: 12, letterSpacing: 0.8 },

  weekRow: { flexDirection: "row", marginTop: spacing.md, paddingHorizontal: spacing.xl, marginBottom: 4 },
  weekLabel: { flex: 1, textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 11, letterSpacing: 1.2 },

  grid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: spacing.xl },
  cell: {
    alignItems: "center",
    paddingTop: 8, paddingBottom: 6, gap: 4,
    borderBottomWidth: 1, borderRightWidth: 1, borderColor: colors.border,
  },
  cellSelected: { backgroundColor: colors.surfaceInverse, borderColor: colors.surfaceInverse },
  cellToday: { backgroundColor: colors.brandTertiary },
  cellNum: { fontFamily: "Georgia", fontSize: 18, color: colors.onSurface },
  barsCol: { alignItems: "center", gap: 3, marginTop: 2 },
  eventLine: { width: 22, height: 3 },
  moreText: { fontSize: 9, color: colors.onSurfaceTertiary, marginTop: 1 },

  detailHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.xl, paddingHorizontal: spacing.xl },
  sectionTitle: { fontFamily: "Georgia", fontSize: 20, color: colors.onSurface },
  empty: { color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: spacing.md },

  eventRow: { flexDirection: "row", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  eventBar: { width: 3, alignSelf: "stretch" },
  eventTime: { color: colors.onSurfaceTertiary, fontSize: 11, letterSpacing: 1, textTransform: "uppercase" },
  eventTitle: { fontFamily: "Georgia", fontSize: 17, color: colors.onSurface, marginTop: 2 },
  eventMeta: { color: colors.onSurfaceSecondary, fontSize: 13, marginTop: 2 },
});
