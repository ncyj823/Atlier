import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator,
  Modal, TextInput, KeyboardAvoidingView, Platform,
} from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect, Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system/legacy";
import { api, Project, Client, PdfMeta, CanvasStroke } from "@/src/api";
import { colors, spacing } from "@/src/theme";
import MannequinCanvas from "@/src/MannequinCanvas";

function fmtDate(d?: string | null) {
  if (!d) return "—";
  return new Date(d + (d.length === 10 ? "T00:00:00" : "")).toLocaleDateString([], {
    day: "numeric", month: "short", year: "numeric",
  });
}

export default function ProjectDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [project, setProject] = useState<Project | null>(null);
  const [client, setClient] = useState<Client | null>(null);
  const [pdfs, setPdfs] = useState<PdfMeta[]>([]);
  const [canvasInit, setCanvasInit] = useState<{ gender: "female" | "male"; strokes: CanvasStroke[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showCanvas, setShowCanvas] = useState(false);

  // Payment edit modal
  const [payModal, setPayModal] = useState(false);
  const [payForm, setPayForm] = useState({ total: "", paid: "" });

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const d = await api.getProject(id);
      setProject(d.project);
      setClient(d.client);
      setPdfs(d.pdfs);
      setCanvasInit({ gender: d.canvas.gender || "female", strokes: d.canvas.strokes || [] });
    } finally { setLoading(false); }
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onUpload = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: "application/pdf", copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const f = res.assets[0];
      setUploading(true);
      const data = await FileSystem.readAsStringAsync(f.uri, { encoding: FileSystem.EncodingType.Base64 });
      await api.uploadProjectPdf(id!, f.name || "document.pdf", data);
      load();
    } finally { setUploading(false); }
  };

  const toggleStatus = async () => {
    if (!project) return;
    const next = project.status === "completed" ? "ongoing" : "completed";
    await api.updateProject(project.id, { status: next });
    load();
  };

  const openPay = () => {
    if (!project) return;
    setPayForm({ total: String(project.total_amount || 0), paid: String(project.paid_amount || 0) });
    setPayModal(true);
  };

  const savePay = async () => {
    if (!project) return;
    await api.updateProject(project.id, {
      total_amount: parseFloat(payForm.total || "0"),
      paid_amount: parseFloat(payForm.paid || "0"),
    });
    setPayModal(false);
    load();
  };

  const saveCanvas = async (data: { gender: "female" | "male"; strokes: CanvasStroke[] }) => {
    if (!id) return;
    await api.saveCanvas(id, data);
    setCanvasInit(data);
  };

  if (loading || !project) {
    return (
      <View style={{ flex: 1, justifyContent: "center", backgroundColor: colors.surface }}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

  const pct = project.total_amount > 0 ? Math.min(100, Math.max(0, (project.paid_amount / project.total_amount) * 100)) : 0;
  const remaining = Math.max(0, project.total_amount - project.paid_amount);

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingBottom: spacing.xxxl }}>
        <View style={[styles.hero, { paddingTop: insets.top + spacing.md }]}>
          <View style={styles.heroHeader}>
            <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
              <Feather name="arrow-left" color={colors.onSurface} size={20} />
            </Pressable>
            <Pressable testID="toggle-status" onPress={toggleStatus} style={[styles.statusPill, project.status === "completed" && styles.statusPillDone]}>
              <Feather name={project.status === "completed" ? "check-circle" : "circle"} size={12} color={project.status === "completed" ? colors.success : colors.onSurfaceSecondary} />
              <Text style={[styles.statusText, project.status === "completed" && { color: colors.success }]}>{project.status}</Text>
            </Pressable>
          </View>
          <Text style={styles.kicker}>Atelier · Project</Text>
          <Pressable
            testID="client-link"
            onPress={() => client && router.push(`/client/${client.id}` as any)}
            style={styles.clientLink}
          >
            <Text style={styles.clientLinkText}>{client?.name || "—"}</Text>
            <Feather name="external-link" size={12} color={colors.brand} />
          </Pressable>
          <Text style={styles.h1} testID="project-title">{project.title}</Text>
          <View style={styles.heroMetaRow}>
            <Feather name="map-pin" size={12} color={colors.onSurfaceSecondary} />
            <Text style={styles.heroMeta}>{project.delivery_location || "No location"}</Text>
          </View>
        </View>

        <View style={styles.datesRow}>
          <View style={styles.dateCol}>
            <Text style={styles.dateLabel}>Created</Text>
            <Text style={styles.dateValue}>{fmtDate(project.created_at)}</Text>
          </View>
          <View style={styles.dateCol}>
            <Text style={styles.dateLabel}>Deadline</Text>
            <Text style={styles.dateValue}>{fmtDate(project.deadline)}</Text>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Payment</Text>
            <Pressable testID="edit-payment" onPress={openPay} style={styles.linkBtn}>
              <Feather name="edit-2" size={12} color={colors.brand} />
              <Text style={styles.linkBtnText}>Edit</Text>
            </Pressable>
          </View>
          {project.total_amount > 0 ? (
            <>
              <View style={styles.bigProgress}>
                <View style={[styles.bigProgressFill, { width: `${pct}%` }]} />
              </View>
              <View style={styles.paymentRow}>
                <View>
                  <Text style={styles.paymentKicker}>Paid</Text>
                  <Text style={[styles.paymentAmount, { color: colors.success }]}>₹{project.paid_amount.toLocaleString()}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.paymentKicker}>Remaining</Text>
                  <Text style={[styles.paymentAmount, { color: remaining > 0 ? colors.warning : colors.success }]}>₹{remaining.toLocaleString()}</Text>
                </View>
              </View>
              <Text style={styles.paymentTotal}>Total project value · ₹{project.total_amount.toLocaleString()}</Text>
            </>
          ) : (
            <Pressable testID="set-amount" onPress={openPay} style={styles.dashedBtn}>
              <Text style={styles.dashedBtnText}>+ Set total amount</Text>
            </Pressable>
          )}
        </View>

        {project.description ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Notes</Text>
            <Text style={styles.notes}>{project.description}</Text>
          </View>
        ) : null}

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Mannequin Canvas</Text>
            <Pressable testID="toggle-canvas" onPress={() => setShowCanvas((v) => !v)} style={styles.linkBtn}>
              <Feather name={showCanvas ? "chevron-up" : "edit-3"} size={12} color={colors.brand} />
              <Text style={styles.linkBtnText}>{showCanvas ? "Hide" : "Open"}</Text>
            </Pressable>
          </View>
          {showCanvas && canvasInit ? (
            <MannequinCanvas initial={canvasInit} onSave={saveCanvas} />
          ) : (
            <Pressable testID="open-canvas" onPress={() => setShowCanvas(true)} style={styles.canvasPreview}>
              <Feather name="edit-3" size={20} color={colors.brand} />
              <Text style={styles.canvasPreviewText}>
                {canvasInit && canvasInit.strokes.length > 0
                  ? `${canvasInit.strokes.length} stroke${canvasInit.strokes.length === 1 ? "" : "s"} · tap to edit`
                  : "Tap to sketch on the mannequin"}
              </Text>
            </Pressable>
          )}
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Design Sheets</Text>
            <Pressable testID="upload-pdf" onPress={onUpload} disabled={uploading} style={styles.linkBtn}>
              {uploading ? <ActivityIndicator color={colors.brand} /> : <>
                <Feather name="upload" color={colors.brand} size={12} />
                <Text style={styles.linkBtnText}>Upload PDF</Text>
              </>}
            </Pressable>
          </View>
          {pdfs.length === 0 ? (
            <Text style={styles.empty}>No design sheets yet.</Text>
          ) : (
            pdfs.map((p) => (
              <View key={p.id} style={styles.pdfRow} testID={`pdf-row-${p.id}`}>
                <Feather name="file-text" color={colors.onSurfaceSecondary} size={18} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.pdfName}>{p.name}</Text>
                  <Text style={styles.pdfMeta}>{new Date(p.uploaded_at).toLocaleDateString()} · {(p.size_bytes/1024).toFixed(0)} KB</Text>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>

      <Modal visible={payModal} animationType="slide" transparent onRequestClose={() => setPayModal(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <Pressable style={styles.backdrop} onPress={() => setPayModal(false)} />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={{ padding: spacing.xl, gap: spacing.md }}>
              <Text style={styles.kicker}>Payment</Text>
              <Text style={styles.sheetTitle}>Update amounts</Text>
              <Text style={styles.fieldLabel}>Total amount (₹)</Text>
              <TextInput testID="pay-total" value={payForm.total} onChangeText={(v) => setPayForm({ ...payForm, total: v })} keyboardType="numeric" style={styles.fieldInput} />
              <Text style={styles.fieldLabel}>Paid so far (₹)</Text>
              <TextInput testID="pay-paid" value={payForm.paid} onChangeText={(v) => setPayForm({ ...payForm, paid: v })} keyboardType="numeric" style={styles.fieldInput} />
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <Pressable testID="save-pay" onPress={savePay} style={styles.primaryBtn}>
                  <Text style={styles.primaryBtnText}>Save</Text>
                </Pressable>
                <Pressable onPress={() => setPayModal(false)} style={styles.ghostBtn}>
                  <Text style={styles.ghostBtnText}>Cancel</Text>
                </Pressable>
              </View>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: spacing.xl, paddingBottom: spacing.lg, backgroundColor: colors.surfaceSecondary, gap: 4 },
  heroHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.lg },
  iconBtn: { padding: spacing.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: 999, backgroundColor: colors.surface },
  statusPillDone: { borderColor: colors.success },
  statusText: { fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase", color: colors.onSurfaceSecondary },

  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  clientLink: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.xs },
  clientLinkText: { color: colors.brand, fontSize: 13, letterSpacing: 1, textTransform: "uppercase" },
  h1: { fontFamily: "Georgia", fontSize: 30, color: colors.onSurface, marginTop: 4, lineHeight: 36 },
  heroMetaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.xs },
  heroMeta: { color: colors.onSurfaceSecondary, fontSize: 14 },

  datesRow: { flexDirection: "row", paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, borderBottomWidth: 1, borderColor: colors.border, gap: spacing.xl },
  dateCol: { flex: 1 },
  dateLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  dateValue: { fontFamily: "Georgia", fontSize: 16, color: colors.onSurface, marginTop: 2 },

  section: { paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, borderBottomWidth: 1, borderColor: colors.border, gap: spacing.sm },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sectionTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  linkBtnText: { color: colors.brand, fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase" },

  notes: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginTop: 4 },

  bigProgress: { height: 12, backgroundColor: colors.surfaceTertiary, marginTop: spacing.sm, overflow: "hidden" },
  bigProgressFill: { height: "100%", backgroundColor: colors.brand },
  paymentRow: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm },
  paymentKicker: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  paymentAmount: { fontFamily: "Georgia", fontSize: 22, marginTop: 2 },
  paymentTotal: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: spacing.sm, textAlign: "center" },

  dashedBtn: { padding: spacing.lg, borderWidth: 1, borderColor: colors.borderStrong, borderStyle: "dashed", alignItems: "center" },
  dashedBtnText: { color: colors.brand, fontSize: 13, letterSpacing: 1.5, textTransform: "uppercase" },

  canvasPreview: { padding: spacing.lg, borderWidth: 1, borderColor: colors.borderStrong, borderStyle: "dashed", alignItems: "center", gap: spacing.sm },
  canvasPreviewText: { color: colors.onSurfaceSecondary, fontSize: 13 },

  empty: { color: colors.onSurfaceTertiary, fontStyle: "italic" },
  pdfRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border },
  pdfName: { fontFamily: "Georgia", fontSize: 16, color: colors.onSurface },
  pdfMeta: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,25,24,0.4)" },
  sheet: { backgroundColor: colors.surface, marginTop: "auto", borderTopWidth: 1, borderColor: colors.borderStrong },
  sheetTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface, marginBottom: spacing.sm },
  fieldLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  fieldInput: { borderBottomWidth: 1, borderColor: colors.borderStrong, paddingVertical: 8, fontSize: 16, color: colors.onSurface, fontFamily: "Georgia" },
  primaryBtn: { backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12 },
  primaryBtnText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12 },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
});
