import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Share,
} from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect, Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api, Client, Project } from "@/src/api";
import { colors, spacing } from "@/src/theme";

function fmtDeadline(d?: string | null) {
  if (!d) return "No deadline";
  return new Date(d + (d.length === 10 ? "T00:00:00" : "")).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

export default function ClientDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [client, setClient] = useState<Client | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [c, pr] = await Promise.all([
        api.getClient(id),
        api.clientProjects(id),
      ]);
      setClient(c.client);
      setProjects(pr);
    } finally { setLoading(false); }
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onShare = async () => {
    if (!id) return;
    const r = await api.share(id);
    setShareUrl(r.url);
    try { await Share.share({ message: `${client?.name || "Client"}'s profile · ${r.url}` }); } catch {}
  };

  if (loading || !client) {
    return (
      <View style={{ flex: 1, justifyContent: "center", backgroundColor: colors.surface }}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  const ongoing = projects.filter((p) => p.status === "ongoing").length;
  const completed = projects.filter((p) => p.status === "completed").length;

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
        <View style={[styles.hero, { paddingTop: insets.top + spacing.md }]}>
          <View style={styles.heroHeader}>
            <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
              <Feather name="arrow-left" color={colors.onSurface} size={20} />
            </Pressable>
            <Pressable testID="share-btn" onPress={onShare} style={styles.iconBtn}>
              <Feather name="share-2" color={colors.onSurface} size={18} />
            </Pressable>
          </View>
          <Text style={styles.kicker}>Atelier · Client</Text>
          <Text style={styles.h1} testID="client-name">{client.name}</Text>
          {client.email ? <Text style={styles.heroMeta}>{client.email}</Text> : null}
          {client.whatsapp ? <Text style={styles.heroMeta}>{client.whatsapp}</Text> : null}

          <View style={styles.statsRow}>
            <View style={styles.statCol}>
              <Text style={styles.statValue}>{projects.length}</Text>
              <Text style={styles.statLabel}>Projects</Text>
            </View>
            <View style={styles.statCol}>
              <Text style={[styles.statValue, { color: colors.warning }]}>{ongoing}</Text>
              <Text style={styles.statLabel}>Ongoing</Text>
            </View>
            <View style={styles.statCol}>
              <Text style={[styles.statValue, { color: colors.success }]}>{completed}</Text>
              <Text style={styles.statLabel}>Completed</Text>
            </View>
          </View>

          {shareUrl ? (
            <View style={styles.shareBox} testID="share-url-box">
              <Text style={styles.shareLabel}>Shareable link</Text>
              <Text style={styles.shareUrl} numberOfLines={2}>{shareUrl}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Measurements</Text>
          {Object.keys(client.measurements || {}).length === 0 ? (
            <Text style={styles.empty}>No measurements on file.</Text>
          ) : (
            <View style={{ gap: 4 }}>
              {Object.entries(client.measurements).map(([k, v]) => (
                <View key={k} style={styles.kvRow}>
                  <Text style={styles.kvKey}>{k}</Text>
                  <Text style={styles.kvVal}>{String(v)}</Text>
                </View>
              ))}
            </View>
          )}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Projects</Text>
          {projects.length === 0 ? (
            <Text style={styles.empty}>No projects yet for this client.</Text>
          ) : (
            projects.map((p) => (
              <Pressable
                key={p.id}
                testID={`client-project-${p.id}`}
                onPress={() => router.push(`/project/${p.id}` as any)}
                style={styles.projectRow}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.projectTitle}>{p.title}</Text>
                  <Text style={styles.projectMeta}>
                    {fmtDeadline(p.deadline)} · {p.delivery_location || "no location"}
                  </Text>
                </View>
                <View style={[styles.smallPill, p.status === "completed" && { borderColor: colors.success }]}>
                  <Text style={[styles.smallPillText, p.status === "completed" && { color: colors.success }]}>{p.status}</Text>
                </View>
                <Feather name="chevron-right" color={colors.onSurfaceTertiary} size={16} />
              </Pressable>
            ))
          )}
        </View>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl, backgroundColor: colors.surfaceSecondary, gap: 4 },
  heroHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.lg },
  iconBtn: { padding: spacing.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  h1: { fontFamily: "Georgia", fontSize: 34, color: colors.onSurface, marginTop: 4 },
  heroMeta: { color: colors.onSurfaceSecondary, fontSize: 14 },

  statsRow: { flexDirection: "row", marginTop: spacing.lg, gap: spacing.lg },
  statCol: { alignItems: "flex-start" },
  statValue: { fontFamily: "Georgia", fontSize: 26, color: colors.onSurface },
  statLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, marginTop: 2 },

  shareBox: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginTop: spacing.md },
  shareLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, marginBottom: 4 },
  shareUrl: { fontSize: 13, color: colors.brand },

  section: { paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, borderBottomWidth: 1, borderColor: colors.border },
  sectionTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface, marginBottom: spacing.md },
  empty: { color: colors.onSurfaceTertiary, fontStyle: "italic" },

  kvRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: 1, borderColor: colors.border },
  kvKey: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 11, color: colors.onSurfaceTertiary },
  kvVal: { fontSize: 14, color: colors.onSurface },

  projectRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border,
  },
  projectTitle: { fontFamily: "Georgia", fontSize: 17, color: colors.onSurface },
  projectMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  smallPill: { paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: 999 },
  smallPillText: { fontSize: 9, letterSpacing: 1.5, textTransform: "uppercase", color: colors.onSurfaceSecondary },
});
