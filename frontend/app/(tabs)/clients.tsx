import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, Modal,
  TextInput, KeyboardAvoidingView, Platform, ScrollView,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import { api, Client } from "@/src/api";
import { colors, spacing } from "@/src/theme";

export default function ClientsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", whatsapp: "", notes: "",
    bust: "", waist: "", hip: "", shoulder: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listClients();
      setClients(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onCreate = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const measurements: any = {};
      if (form.bust) measurements.Bust = form.bust;
      if (form.waist) measurements.Waist = form.waist;
      if (form.hip) measurements.Hip = form.hip;
      if (form.shoulder) measurements.Shoulder = form.shoulder;
      await api.createClient({
        name: form.name.trim(),
        email: form.email.trim(),
        whatsapp: form.whatsapp.trim(),
        notes: form.notes.trim(),
        measurements,
      });
      setModal(false);
      setForm({ name: "", email: "", whatsapp: "", notes: "", bust: "", waist: "", hip: "", shoulder: "" });
      load();
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.kicker}>Atelier · Clients</Text>
          <Text style={styles.h1} testID="clients-title">Directory</Text>
        </View>
        <Pressable testID="open-create-client" onPress={() => setModal(true)} style={styles.headerBtn}>
          <Feather name="plus" color={colors.onSurface} size={18} />
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing.xxl }} />
      ) : (
        <FlatList
          data={clients}
          keyExtractor={(c) => c.id}
          contentContainerStyle={{ paddingBottom: spacing.xxxl }}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Feather name="users" size={28} color={colors.onSurfaceTertiary} />
              <Text style={styles.emptyText}>No clients yet. Add your first client.</Text>
            </View>
          }
          renderItem={({ item }) => (
            <Pressable
              testID={`client-card-${item.id}`}
              onPress={() => router.push(`/client/${item.id}` as any)}
              style={styles.row}
            >
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{item.name.split(" ").map(p => p[0]).slice(0,2).join("")}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowName}>{item.name}</Text>
                {item.email ? <Text style={styles.rowMeta}>{item.email}</Text> : null}
                {item.whatsapp ? <Text style={styles.rowMeta}>{item.whatsapp}</Text> : null}
              </View>
              <Feather name="chevron-right" color={colors.onSurfaceTertiary} size={18} />
            </Pressable>
          )}
        />
      )}

      <Pressable
        testID="fab-create-client"
        onPress={() => setModal(true)}
        style={[styles.fab, { bottom: insets.bottom + 90 }]}
      >
        <Feather name="plus" color={colors.onBrandPrimary} size={20} />
        <Text style={styles.fabText}>Create Client</Text>
      </Pressable>

      <Modal visible={modal} animationType="slide" transparent onRequestClose={() => setModal(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <Pressable style={styles.modalBackdrop} onPress={() => setModal(false)} />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }} keyboardShouldPersistTaps="handled">
              <Text style={styles.kicker}>New Client</Text>
              <Text style={styles.sheetTitle}>Add to your atelier</Text>

              <Field label="Name" value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} testID="field-name" />
              <Field label="Email" value={form.email} onChangeText={(v) => setForm({ ...form, email: v })} testID="field-email" keyboardType="email-address" />
              <Field label="WhatsApp" value={form.whatsapp} onChangeText={(v) => setForm({ ...form, whatsapp: v })} testID="field-whatsapp" />
              <Field label="Notes" value={form.notes} onChangeText={(v) => setForm({ ...form, notes: v })} testID="field-notes" multiline />

              <Text style={[styles.kicker, { marginTop: spacing.md }]}>Measurements</Text>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}><Field label="Bust" value={form.bust} onChangeText={(v) => setForm({ ...form, bust: v })} testID="field-bust" /></View>
                <View style={{ flex: 1 }}><Field label="Waist" value={form.waist} onChangeText={(v) => setForm({ ...form, waist: v })} testID="field-waist" /></View>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}><Field label="Hip" value={form.hip} onChangeText={(v) => setForm({ ...form, hip: v })} testID="field-hip" /></View>
                <View style={{ flex: 1 }}><Field label="Shoulder" value={form.shoulder} onChangeText={(v) => setForm({ ...form, shoulder: v })} testID="field-shoulder" /></View>
              </View>

              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <Pressable testID="save-client" onPress={onCreate} disabled={!form.name.trim() || saving} style={[styles.primaryBtn, (!form.name.trim() || saving) && { opacity: 0.5 }]}>
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Save client</Text>}
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

  empty: { alignItems: "center", paddingVertical: spacing.xxxl, gap: spacing.sm },
  emptyText: { color: colors.onSurfaceTertiary, fontStyle: "italic", textAlign: "center" },

  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  avatar: {
    width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  avatarText: { fontFamily: "Georgia", fontSize: 16, color: colors.onBrandTertiary },
  rowName: { fontFamily: "Georgia", fontSize: 18, color: colors.onSurface },
  rowMeta: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },

  fab: {
    position: "absolute", right: spacing.xl,
    backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12,
    flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 999,
  },
  fabText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },

  modalBackdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,25,24,0.4)" },
  sheet: { backgroundColor: colors.surface, marginTop: "auto", maxHeight: "92%", borderTopWidth: 1, borderColor: colors.borderStrong },
  sheetTitle: { fontFamily: "Georgia", fontSize: 24, color: colors.onSurface, marginBottom: spacing.sm },

  fieldLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  fieldInput: {
    borderBottomWidth: 1, borderColor: colors.borderStrong, paddingVertical: 8,
    fontSize: 16, color: colors.onSurface, fontFamily: "Georgia",
  },

  primaryBtn: { backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12 },
  primaryBtnText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12 },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
});
