import { useCallback, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator,
  Modal, TextInput, KeyboardAvoidingView, Platform, Share,
} from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect, Stack } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system";
import { api, Client, InvoiceItem, PdfMeta } from "@/src/api";
import { colors, spacing } from "@/src/theme";

export default function ClientDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [client, setClient] = useState<Client | null>(null);
  const [pdfs, setPdfs] = useState<PdfMeta[]>([]);
  const [items, setItems] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const [invModal, setInvModal] = useState(false);
  const [editingItem, setEditingItem] = useState<InvoiceItem | null>(null);
  const [form, setForm] = useState({ description: "", amount: "", status: "pending" as "pending" | "cleared" });

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await api.getClient(id);
      setClient(data.client);
      setPdfs(data.pdfs);
      setItems(data.invoice.items || []);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onUpload = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: "application/pdf", copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const f = res.assets[0];
      setUploading(true);
      const data = await FileSystem.readAsStringAsync(f.uri, { encoding: FileSystem.EncodingType.Base64 });
      await api.uploadPdf(id!, f.name || "document.pdf", data);
      load();
    } catch (e) {
      console.warn("upload failed", e);
    } finally {
      setUploading(false);
    }
  };

  const onShare = async () => {
    if (!id) return;
    const r = await api.share(id);
    setShareUrl(r.url);
    try {
      await Share.share({ message: `View ${client?.name || "client"}'s profile: ${r.url}` });
    } catch {}
  };

  const onOpenAdd = () => {
    setEditingItem(null);
    setForm({ description: "", amount: "", status: "pending" });
    setInvModal(true);
  };

  const onOpenEdit = (it: InvoiceItem) => {
    setEditingItem(it);
    setForm({ description: it.description, amount: String(it.amount), status: it.status });
    setInvModal(true);
  };

  const onSaveInv = async () => {
    if (!id || !form.description.trim()) return;
    const body = { description: form.description.trim(), amount: parseFloat(form.amount || "0"), status: form.status };
    if (editingItem) await api.updateInvoiceItem(id, editingItem.id, body);
    else await api.addInvoiceItem(id, body);
    setInvModal(false);
    load();
  };

  const onDeleteInv = async (item_id: string) => {
    if (!id) return;
    await api.deleteInvoiceItem(id, item_id);
    load();
  };

  const totalPending = items.filter(i => i.status === "pending").reduce((s, i) => s + i.amount, 0);
  const totalCleared = items.filter(i => i.status === "cleared").reduce((s, i) => s + i.amount, 0);

  if (loading || !client) {
    return (
      <View style={{ flex: 1, justifyContent: "center", backgroundColor: colors.surface }}>
        <ActivityIndicator color={colors.brand} />
      </View>
    );
  }

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
          {shareUrl ? (
            <View style={styles.shareBox} testID="share-url-box">
              <Text style={styles.shareLabel}>Shareable link</Text>
              <Text style={styles.shareUrl} numberOfLines={2}>{shareUrl}</Text>
            </View>
          ) : null}
        </View>

        <Section title="Measurements">
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
        </Section>

        <Section
          title="Design Sheets"
          action={
            <Pressable testID="upload-pdf" onPress={onUpload} disabled={uploading} style={styles.sectionAction}>
              {uploading ? <ActivityIndicator color={colors.brand} /> : <>
                <Feather name="upload" color={colors.brand} size={14} />
                <Text style={styles.sectionActionText}>Upload PDF</Text>
              </>}
            </Pressable>
          }
        >
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
        </Section>

        <Section
          title="Invoice"
          action={
            <Pressable testID="add-invoice-item" onPress={onOpenAdd} style={styles.sectionAction}>
              <Feather name="plus" color={colors.brand} size={14} />
              <Text style={styles.sectionActionText}>Add item</Text>
            </Pressable>
          }
        >
          {items.length === 0 ? (
            <Text style={styles.empty}>No invoice items.</Text>
          ) : (
            <>
              {items.map((it) => (
                <Pressable key={it.id} onPress={() => onOpenEdit(it)} testID={`invoice-row-${it.id}`} style={styles.invRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.invDesc}>{it.description}</Text>
                    <Text style={[styles.invStatus, { color: it.status === "cleared" ? colors.success : colors.warning }]}>
                      {it.status}
                    </Text>
                  </View>
                  <Text style={styles.invAmount}>₹{it.amount.toFixed(2)}</Text>
                  <Pressable onPress={() => onDeleteInv(it.id)} testID={`delete-inv-${it.id}`} style={{ padding: 6 }}>
                    <Feather name="x" color={colors.onSurfaceTertiary} size={16} />
                  </Pressable>
                </Pressable>
              ))}
              <View style={styles.totalsRow}>
                <Text style={styles.totalsLabel}>Pending</Text>
                <Text style={[styles.totalsAmt, { color: colors.warning }]}>₹{totalPending.toFixed(2)}</Text>
              </View>
              <View style={styles.totalsRow}>
                <Text style={styles.totalsLabel}>Cleared</Text>
                <Text style={[styles.totalsAmt, { color: colors.success }]}>₹{totalCleared.toFixed(2)}</Text>
              </View>
            </>
          )}
        </Section>
      </ScrollView>

      <Modal visible={invModal} animationType="slide" transparent onRequestClose={() => setInvModal(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <Pressable style={styles.backdrop} onPress={() => setInvModal(false)} />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={{ padding: spacing.xl, gap: spacing.md }}>
              <Text style={styles.kicker}>{editingItem ? "Update item" : "New item"}</Text>
              <Text style={styles.sheetTitle}>{editingItem ? "Edit invoice line" : "Add invoice line"}</Text>

              <Text style={styles.fieldLabel}>Description</Text>
              <TextInput
                testID="inv-description"
                value={form.description}
                onChangeText={(v) => setForm({ ...form, description: v })}
                style={styles.fieldInput}
              />
              <Text style={styles.fieldLabel}>Amount (₹)</Text>
              <TextInput
                testID="inv-amount"
                value={form.amount}
                onChangeText={(v) => setForm({ ...form, amount: v })}
                keyboardType="numeric"
                style={styles.fieldInput}
              />
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                {(["pending", "cleared"] as const).map((s) => (
                  <Pressable
                    key={s}
                    testID={`inv-status-${s}`}
                    onPress={() => setForm({ ...form, status: s })}
                    style={[styles.statusChip, form.status === s && styles.statusChipActive]}
                  >
                    <Text style={[styles.statusChipText, form.status === s && { color: "#fff" }]}>{s}</Text>
                  </Pressable>
                ))}
              </View>

              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <Pressable testID="save-inv" onPress={onSaveInv} style={styles.primaryBtn}>
                  <Text style={styles.primaryBtnText}>{editingItem ? "Update" : "Add"} & email client</Text>
                </Pressable>
                <Pressable onPress={() => setInvModal(false)} style={styles.ghostBtn}>
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

function Section({ title, action, children }: { title: string; action?: any; children: any }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {action}
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xl, backgroundColor: colors.surfaceSecondary, gap: 4 },
  heroHeader: { flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.lg },
  iconBtn: { padding: spacing.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  kicker: { letterSpacing: 2.4, textTransform: "uppercase", color: colors.brand, fontSize: 11 },
  h1: { fontFamily: "Georgia", fontSize: 36, color: colors.onSurface, marginTop: 4 },
  heroMeta: { color: colors.onSurfaceSecondary, fontSize: 14 },

  shareBox: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, padding: spacing.md, marginTop: spacing.md },
  shareLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary, marginBottom: 4 },
  shareUrl: { fontSize: 13, color: colors.brand },

  section: { paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, borderBottomWidth: 1, borderColor: colors.border },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md },
  sectionTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface },
  sectionAction: { flexDirection: "row", alignItems: "center", gap: 4 },
  sectionActionText: { color: colors.brand, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 11 },
  empty: { color: colors.onSurfaceTertiary, fontStyle: "italic" },

  kvRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: 1, borderColor: colors.border },
  kvKey: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 11, color: colors.onSurfaceTertiary },
  kvVal: { fontSize: 14, color: colors.onSurface },

  pdfRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border },
  pdfName: { fontFamily: "Georgia", fontSize: 16, color: colors.onSurface },
  pdfMeta: { color: colors.onSurfaceTertiary, fontSize: 12, marginTop: 2 },

  invRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderColor: colors.border },
  invDesc: { fontFamily: "Georgia", fontSize: 16, color: colors.onSurface },
  invStatus: { fontSize: 10, letterSpacing: 1.5, textTransform: "uppercase", marginTop: 2 },
  invAmount: { fontSize: 16, color: colors.onSurface },
  totalsRow: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm },
  totalsLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 11, color: colors.onSurfaceTertiary },
  totalsAmt: { fontFamily: "Georgia", fontSize: 18 },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(26,25,24,0.4)" },
  sheet: { backgroundColor: colors.surface, marginTop: "auto", borderTopWidth: 1, borderColor: colors.borderStrong },
  sheetTitle: { fontFamily: "Georgia", fontSize: 22, color: colors.onSurface, marginBottom: spacing.sm },
  fieldLabel: { letterSpacing: 1.5, textTransform: "uppercase", fontSize: 10, color: colors.onSurfaceTertiary },
  fieldInput: { borderBottomWidth: 1, borderColor: colors.borderStrong, paddingVertical: 8, fontSize: 16, color: colors.onSurface, fontFamily: "Georgia" },

  statusChip: { paddingHorizontal: spacing.md, paddingVertical: 8, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: 999 },
  statusChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  statusChipText: { fontSize: 12, letterSpacing: 1, textTransform: "uppercase", color: colors.onSurfaceSecondary },

  primaryBtn: { backgroundColor: colors.brand, paddingHorizontal: spacing.lg, paddingVertical: 12 },
  primaryBtnText: { color: colors.onBrandPrimary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
  ghostBtn: { paddingHorizontal: spacing.lg, paddingVertical: 12 },
  ghostBtnText: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, textTransform: "uppercase", fontSize: 12 },
});
