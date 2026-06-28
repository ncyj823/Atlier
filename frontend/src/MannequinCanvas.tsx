import React, { useMemo, useRef, useState } from "react";
import { View, StyleSheet, PanResponder, Pressable, Text } from "react-native";
import Svg, { Path, Image as SvgImage } from "react-native-svg";
import { Feather } from "@expo/vector-icons";
import { colors, spacing } from "@/src/theme";
import type { CanvasStroke } from "@/src/api";

// User-provided mannequin sheets (front + back view inside a single image).
const MANNEQUIN_IMAGES: Record<"female" | "male", string> = {
  female: "https://customer-assets.emergentagent.com/job_style-manager-29/artifacts/dcd23zoo_image.png",
  male:   "https://customer-assets.emergentagent.com/job_style-manager-29/artifacts/foj8l28z_image.png",
};

const STROKE_COLOR = "#1A1918";  // single brand-friendly ink
const STROKE_WIDTH = 3;          // medium, round tip

type Props = {
  initial: { gender: "female" | "male"; strokes: CanvasStroke[] };
  onSave: (data: { gender: "female" | "male"; strokes: CanvasStroke[] }) => Promise<void> | void;
  height?: number;
};

export default function MannequinCanvas({ initial, onSave, height = 520 }: Props) {
  const [gender, setGender] = useState<"female" | "male">(initial.gender || "female");
  const [strokes, setStrokes] = useState<CanvasStroke[]>(initial.strokes || []);
  const [current, setCurrent] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number>(0);
  const currentRef = useRef("");

  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (evt) => {
      const { locationX, locationY } = evt.nativeEvent;
      currentRef.current = `M${locationX.toFixed(1)} ${locationY.toFixed(1)}`;
      setCurrent(currentRef.current);
    },
    onPanResponderMove: (evt) => {
      const { locationX, locationY } = evt.nativeEvent;
      currentRef.current += ` L${locationX.toFixed(1)} ${locationY.toFixed(1)}`;
      setCurrent(currentRef.current);
    },
    onPanResponderRelease: () => {
      const d = currentRef.current;
      if (d && d.includes("L")) {
        setStrokes((prev) => [...prev, { d, color: STROKE_COLOR, width: STROKE_WIDTH }]);
      }
      currentRef.current = "";
      setCurrent("");
    },
  }), []);

  const undo = () => setStrokes((s) => s.slice(0, -1));

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({ gender, strokes });
      setSavedAt(Date.now());
    } finally {
      setSaving(false);
    }
  };

  const justSaved = savedAt && Date.now() - savedAt < 2500;

  return (
    <View style={styles.wrap} testID="mannequin-canvas">
      <View style={styles.toolbar}>
        <View style={styles.segment}>
          <Pressable
            testID="gender-female"
            onPress={() => setGender("female")}
            style={[styles.segmentBtn, gender === "female" && styles.segmentBtnActive]}
          >
            <Text style={[styles.segmentText, gender === "female" && { color: "#fff" }]}>Female</Text>
          </Pressable>
          <Pressable
            testID="gender-male"
            onPress={() => setGender("male")}
            style={[styles.segmentBtn, gender === "male" && styles.segmentBtnActive]}
          >
            <Text style={[styles.segmentText, gender === "male" && { color: "#fff" }]}>Male</Text>
          </Pressable>
        </View>

        <View style={styles.tools}>
          <Pressable testID="canvas-undo" onPress={undo} disabled={strokes.length === 0} style={[styles.toolBtn, strokes.length === 0 && { opacity: 0.4 }]}>
            <Feather name="rotate-ccw" color={colors.onSurface} size={16} />
          </Pressable>
          <Pressable testID="canvas-save" onPress={handleSave} disabled={saving} style={styles.saveBtn}>
            <Text style={styles.saveBtnText}>{saving ? "Saving…" : justSaved ? "Saved ✓" : "Save"}</Text>
          </Pressable>
        </View>
      </View>

      <View
        style={[styles.canvas, { height }]}
        {...responder.panHandlers}
        testID="canvas-surface"
      >
        <Svg width="100%" height="100%" viewBox="0 0 200 500" preserveAspectRatio="xMidYMid meet">
          <SvgImage
            href={MANNEQUIN_IMAGES[gender]}
            x="0"
            y="0"
            width="200"
            height="500"
            preserveAspectRatio="xMidYMid meet"
          />
        </Svg>
        <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
          {strokes.map((s, i) => (
            <Path
              key={`s-${i}`}
              d={s.d}
              stroke={STROKE_COLOR}
              strokeWidth={STROKE_WIDTH}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {current ? (
            <Path
              d={current}
              stroke={STROKE_COLOR}
              strokeWidth={STROKE_WIDTH}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null}
        </Svg>
      </View>

      <Text style={styles.hint}>
        {strokes.length === 0
          ? "Draw on the mannequin. Tap Save to keep your sketch."
          : `${strokes.length} stroke${strokes.length === 1 ? "" : "s"} · drawing auto-keeps until you tap Save`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: colors.surface },
  toolbar: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderColor: colors.border,
  },
  segment: { flexDirection: "row", borderWidth: 1, borderColor: colors.borderStrong },
  segmentBtn: { paddingHorizontal: spacing.md, paddingVertical: 8 },
  segmentBtnActive: { backgroundColor: colors.surfaceInverse },
  segmentText: { fontSize: 12, letterSpacing: 1, textTransform: "uppercase", color: colors.onSurface },

  tools: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  toolBtn: { padding: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  saveBtn: { backgroundColor: colors.brand, paddingHorizontal: spacing.md, paddingVertical: 8 },
  saveBtnText: { color: "#fff", fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },

  canvas: { backgroundColor: "#fff" },
  hint: { fontSize: 11, color: colors.onSurfaceTertiary, padding: spacing.sm, textAlign: "center", borderTopWidth: 1, borderColor: colors.border },
});
