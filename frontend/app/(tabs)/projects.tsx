import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, Modal,
  TextInput, KeyboardAvoidingView, Platform, ScrollView,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api, Project, Client } from "@/src/api";
import { colors, spacing } from "@/src/theme";

function fmtDeadline(deadline: string | null) {
  if (!deadline) return "No deadline";
  const d = new Date(deadline + (deadline.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

function daysUntil(deadline: string | null): number | null {
  if (!deadline) return null;
  const d = new Date(deadline + (deadline.length === 10 ? "T00:00:00" : ""));
  const ms = d.getTime() - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

export default function ProjectsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({
    client_id: "", title: "", delivery_location: "", deadline: "",
    description: "", total_amount: "", paid_amount: "",
    mannequin_gender: "female" as "female" | "male",
  });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [pr, cl] = await Promise.all([api.listProjects(), api.listClients()]);
      setProjects(pr);
      setClients(cl);
    } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openCreate = () => {
    setForm({ client_id: "", title: "", delivery_location: "", deadline: "", description: "", total_amount: "", paid_amount: "", mannequin_gender: "female" });
    setModal(true);
  };

  const onCreate = async () => {
    if (!form.client_id || !form.title.trim()) return;
    setSaving(true);
    try {
      const created = await api.createProject({
        client_id: form.client_id,
        title: form.title.trim(),
        delivery_location: form.delivery_location.trim(),
        deadline: form.deadline.trim() || null,
        description: form.description.trim(),
        total_amount: parseFloat(form.total_amount || "0"),
        paid_amount: parseFloat(form.paid_amount || "0"),
        mannequin_gender: form.mannequin_gender,
      });
      setModal(false);
      router.push(`/project/${created.id}` as any);
    } finally { setSaving(false); }
  };

  const selectedClient = clients.find((c) => c.id === form.client_id);

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.kicker}>Atelier · Projects</Text>
          <Text style={styles.h1} testID="projects-title">Workbench</Text>
        </View>
        <Pressable testID="open-create-project" onPress={openCreate} style={styles.headerBtn}>
          <Feather name="plus" color={colors.onSurface} size={18} />
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xxl }} />
      ) : (
        <FlatList
          data={projects}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ paddingBottom: spacing.xxxl + 80 }}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Feather name="layers" size={28} color={colors.onSurfaceTertiary} />
              <Text style={styles.emptyText}>No projects yet. Create your first one.</Text>
            </View>
          }
          renderItem={({ item }) => {
            const dl = daysUntil(item.deadline);
            const dlColor = dl == null ? colors.onSurfaceTertiary
              : dl < 0 ? colors.error : dl <= 7 ? colors.warning : colors.onSurfaceSecondary;
            const pct = item.total_amount > 0 ? Math.min(100, Math.max(0, (item.paid_amount / item.total_amount) * 100)) : 0;
            return (
              <Pressable
                testID={`project-card-${item.id}`}
                onPress={() => router.push(`/project/${item.id}` as any)}
                style={styles.card}
              >
                <View style={styles.cardTopRow}>
                  <Text style={styles.cardClient} numberOfLines={1}>{item.client_name || "—"}</Text>
                  <View style={[styles.statusPill, item.status === "completed" && styles.statusPillDone]}>
                    <Text style={[styles.statusText, item.status === "completed" && { color: colors.success }]}>
                      {item.status}
                    </Text>
                  </View>
                </View>
                <View style={styles.cardSubRow}>
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  {item.uid ? <Text style={styles.cardUid}>{item.uid}</Text> : null}
                </View>
                <View style={styles.cardMetaRow}>
                  <Feather name="map-pin" size={11} color={colors.onSurfaceTertiary} />
                  <Text style={styles.cardMetaText}>{item.delivery_location || "No location"}</Text>
                  <View style={styles.dot} />
                  <Feather name="calendar" size={11} color={dlColor} />
                  <Text style={[styles.cardMetaText, { color: dlColor }]}>
                    {fmtDeadline(item.deadline)}
                    {dl != null && dl >= 0 && dl <= 30 ? `  ·  ${dl}d left` : ""}
                    {dl != null && dl < 0 ? "  ·  overdue" : ""}
                  </Text>
                </View>
                {item.total_amount > 0 && (
                  <>
                    <View style={styles.progressBar}>
                      <View style={[styles.progressFill, { width: `${pct}%` }]} />
                    </View>
                    <Text style={styles.progressLabel}>
                      ₹{item.paid_amount.toLocaleString()} of ₹{item.total_amount.toLocaleString()} ·{" "}
                      {item.paid_amount >= item.total_amount ? "Paid in full" : `₹${(item.total_amount - item.paid_amount).toLocaleString()} pending`}
                    </Text>
                  </>
                )}
              </Pressable>
            );
          }}
        />
      )}

      <Pressable
        testID="fab-create-project"
        onPress={openCreate}
        style={[styles.fab, { bottom: insets.bottom + 90 }]}
      >
        <Feather name="plus" color={colors.onBrandPrimary} size={20} />
        <Text style={styles.fabText}>New Project</Text>
      </Pressable>

      <Modal visible={modal} animationType="slide" transparent onRequestClose={() => setModal(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <Pressable style={styles.backdrop} onPress={() => setModal(false)} />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }} keyboardShouldPersistTaps="handled">
              <Text style={styles.kicker}>New Project</Text>
              <Text style={styles.sheetTitle}>Add to your workbench</Text>

              <Text style={styles.fieldLabel}>Client</Text>
              <Pressable testID="pick-client" onPress={() => setPickerOpen(!pickerOpen)} style={styles.pickerBtn}>
                <Text style={[styles.pickerText, !selectedClient && { color: colors.onSurfaceTertiary }]}>
                  {selectedClient ? selectedClient.name : "Select a client"}
                </Text>
                <Feather name={pickerOpen ? "chevron-up" : "chevron-down"} color={colors.onSurfaceSecondary} size={16} />
              </Pressable>
              {pickerOpen && (
                <View style={styles.pickerDropdown}>
                  {clients.length === 0 ? (
                    <Text style={styles.empty}>No clients yet. Create one from a project's client tag.</Text>
                  ) : (
                    clients.map((c) => (
                      <Pressable
                        key={c.id}
                        testID={`client-option-${c.id}`}
                        onPress={() => { setForm((f) => ({ ...f, client_id: c.id })); setPickerOpen(false); }}
                        style={styles.pickerOption}
                      >
                        <Text style={styles.pickerOptionText}>{c.name}</Text>
                      </Pressable>
                    ))
                  )}
                </View>
              )}

              <Field label="Title" value={form.title} onChangeText={(v: string) => setForm({ ...form, title: v })} testID="field-title" />
              <Field label="Delivery location" value={form.delivery_location} onChangeText={(v: string) => setForm({ ...form, delivery_location: v })} testID="field-location" />
              <Field label="Deadline (YYYY-MM-DD)" value={form.deadline} onChangeText={(v: string) => setForm({ ...form, deadline: v })} testID="field-deadline" />
              <Field label="Description / notes" value={form.description} onChangeText={(v: string) => setForm({ ...form, description: v })} multiline testID="field-description" />
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Field label="Total amount (₹)" value={form.total_amount} onChangeText={(v: string) => setForm({ ...form, total_amount: v })} keyboardType="numeric" testID="field-total" />
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Paid so far (₹)" value={form.paid_amount} onChangeText={(v: string) => setForm({ ...form, paid_amount: v })} keyboardType="numeric" testID="field-paid" />
                </View>
              </View>

              <Text style={styles.fieldLabel}>Mannequin</Text>
              <View style={styles.segment}>
                <Pressable testID="form-gender-female" onPress={() => setForm({ ...form, mannequin_gender: "female" })} style={[styles.segmentBtn, form.mannequin_gender === "female" && styles.segmentBtnActive]}>
                  <Text style={[styles.segmentText, form.mannequin_gender === "female" && { color: "#fff" }]}>Female</Text>
                </Pressable>
                <Pressable testID="form-gender-male" onPress={() => setForm({ ...form, mannequin_gender: "male" })} style={[styles.segmentBtn, form.mannequin_gender === "male" && styles.segmentBtnActive]}>
                  <Text style={[styles.segmentText, form.mannequin_gender === "male" && { color: "#fff" }]}>Male</Text>
                </Pressable>
              </View>

              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <Pressable testID="save-project" onPress={onCreate} disabled={!form.client_id || !form.title.trim() || saving} style={[styles.primaryBtn, (!form.client_id || !form.title.trim() || saving) && { opacity: 0.5 }]}>
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Create project</Text>}
                </Pressable>
                <Pressable onPress={() => setModal(false)} style={styles.ghostBtn}>
                  <Text style={styles.ghostBtnText}>Cancel</Text>
                </Pressable>
              </View>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

function Field({ label, value, onChangeText, testID, multiline, keyboardType }: any) {
  return (
    <View style={{ gap: 4 }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChangeText}
        multiline={multiline}
        keyboardType={keyboardType}
        placeholderTextColor={colors.onSurfaceTertiary}
        style={[styles.fieldInput, multiline && { minHeight: 60, textAlignVertical: "top" }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.xl },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginBottom: spacing.lg },
  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  h1: { fontFamily: "Georgia", fontSize: 26, color: colors.onSurface, marginTop: 4 },
  headerBtn: { padding: spacing.sm, borderWidth: 1, borderColor: colors.border },

  empty: { color: colors.onSurfaceTertiary, fontStyle: "italic", textAlign: "center", paddingVertical: spacing.xxl, gap: spacing.sm },
  emptyText: { color: colors.onSurfaceTertiary, fontStyle: "italic", textAlign: "center" },

  card: {
    paddingVertical: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.border, gap: spacing.xs,
  },
  cardTopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  cardClient: { flex: 1, fontFamily: "Georgia", fontSize: 24, color: colors.onSurface, lineHeight: 28 },
  cardSubRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 2, marginBottom: 4 },
  cardTitle: { fontSize: 13, color: colors.onSurfaceSecondary, fontStyle: "italic", flex: 1 },
  cardUid: { fontSize: 10, letterSpacing: 1.5, color: colors.brand, marginLeft: spacing.sm },
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: 999 },
  statusPillDone: { borderColor: colors.success },
  statusText: { fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase", color: colors.onSurfaceSecondary },
  cardMetaRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 },
  cardMetaText: { fontSize: 12, color: colors.onSurfaceSecondary },
  dot: { width: 3, height: 3, borderRadius: 1.5, backgroundColor: colors.onSurfaceTertiary, marginHorizontal: 4 },

  progressBar: { height: 6, backgroundColor: colors.surfaceTertiary, marginTop: 4, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: colors.brand },
  progressLabel: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2, letterSpacing: 0.3 },

  fab: {
    position: "absolute", right: spacing.xl,
    backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12,
    flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 999,
  },
  fabText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,25,24,0.4)" },
  sheet: { backgroundColor: colors.surface, marginTop: "auto", maxHeight: "94%", borderTopWidth: 1, borderColor: colors.borderStrong },
  sheetTitle: { fontFamily: "Georgia", fontSize: 24, color: colors.onSurface, marginBottom: spacing.sm },

  fieldLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  fieldInput: { borderBottomWidth: 1, borderColor: colors.borderStrong, paddingVertical: 8, fontSize: 16, color: colors.onSurface, fontFamily: "Georgia" },

  pickerBtn: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderBottomWidth: 1, borderColor: colors.borderStrong, paddingVertical: 10 },
  pickerText: { fontSize: 16, color: colors.onSurface, fontFamily: "Georgia" },
  pickerDropdown: { borderWidth: 1, borderColor: colors.border, maxHeight: 200, backgroundColor: colors.surfaceSecondary },
  pickerOption: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 1, borderColor: colors.border },
  pickerOptionText: { fontSize: 15, color: colors.onSurface },

  segment: { flexDirection: "row", borderWidth: 1, borderColor: colors.borderStrong, alignSelf: "flex-start" },
  segmentBtn: { paddingHorizontal: spacing.lg, paddingVertical: 10 },
  segmentBtnActive: { backgroundColor: colors.surfaceInverse },
  segmentText: { fontSize: 12, letterSpacing: 1, textTransform: "uppercase", color: colors.onSurface },

  primaryBtn: { backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12 },
  primaryBtnText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12 },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
});
