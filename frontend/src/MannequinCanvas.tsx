import React, { useMemo, useRef, useState } from "react";
import { View, StyleSheet, PanResponder, Pressable, Text } from "react-native";
import Svg, { Path, G } from "react-native-svg";
import { Feather } from "@expo/vector-icons";
import { colors, spacing } from "@/src/theme";
import type { CanvasStroke } from "@/src/api";

// Mannequin silhouette (viewBox 200x500), neutral garment block lines.
const MANNEQUIN: Record<"female" | "male", string[]> = {
  female: [
    "M100 30 c-14 0 -25 11 -25 25 s11 25 25 25 25 -11 25 -25 -11 -25 -25 -25 z", // head
    "M82 80 L118 80 L122 105 L78 105 Z", // neck/shoulders top
    "M60 110 L140 110 L150 200 L130 240 L70 240 L50 200 Z", // torso (hourglass)
    "M70 240 L130 240 L138 320 L120 410 L112 480 L88 480 L80 410 L62 320 Z", // hips → legs
    "M50 110 L20 200 L26 260 L40 195 Z", // left arm
    "M150 110 L180 200 L174 260 L160 195 Z", // right arm
  ],
  male: [
    "M100 30 c-13 0 -23 10 -23 23 s10 23 23 23 23 -10 23 -23 -10 -23 -23 -23 z",
    "M80 78 L120 78 L124 100 L76 100 Z",
    "M50 105 L150 105 L156 220 L150 250 L50 250 L44 220 Z",
    "M50 250 L150 250 L144 360 L132 480 L108 480 L102 360 L98 360 L92 480 L68 480 L56 360 Z",
    "M44 105 L18 210 L26 270 L40 200 Z",
    "M156 105 L182 210 L174 270 L160 200 Z",
  ],
};

type Props = {
  initial: { gender: "female" | "male"; strokes: CanvasStroke[] };
  onSave: (data: { gender: "female" | "male"; strokes: CanvasStroke[] }) => Promise<void> | void;
  height?: number;
};

export default function MannequinCanvas({ initial, onSave, height = 480 }: Props) {
  const [gender, setGender] = useState<"female" | "male">(initial.gender || "female");
  const [strokes, setStrokes] = useState<CanvasStroke[]>(initial.strokes || []);
  const [current, setCurrent] = useState<string>("");
  const [color, setColor] = useState("#A3523B");
  const [width, setWidth] = useState(3);
  const [saving, setSaving] = useState(false);
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
        setStrokes((prev) => [...prev, { d, color, width }]);
      }
      currentRef.current = "";
      setCurrent("");
    },
  }), [color, width]);

  const undo = () => setStrokes((s) => s.slice(0, -1));
  const clear = () => setStrokes([]);

  const handleSave = async () => {
    setSaving(true);
    try { await onSave({ gender, strokes }); } finally { setSaving(false); }
  };

  const PALETTE = [colors.brand, "#1A1918", "#5C6B5D", "#B38A58", "#FFFFFF"];

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
          <Pressable testID="canvas-undo" onPress={undo} style={styles.toolBtn}>
            <Feather name="rotate-ccw" color={colors.onSurface} size={16} />
          </Pressable>
          <Pressable testID="canvas-clear" onPress={clear} style={styles.toolBtn}>
            <Feather name="trash-2" color={colors.onSurface} size={16} />
          </Pressable>
          <Pressable testID="canvas-save" onPress={handleSave} disabled={saving} style={styles.saveBtn}>
            <Text style={styles.saveBtnText}>{saving ? "Saving…" : "Save"}</Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.palette}>
        {PALETTE.map((c) => (
          <Pressable
            key={c}
            testID={`color-${c}`}
            onPress={() => setColor(c)}
            style={[
              styles.colorChip,
              { backgroundColor: c, borderColor: c === "#FFFFFF" ? colors.borderStrong : c },
              color === c && styles.colorChipActive,
            ]}
          />
        ))}
        <View style={{ flex: 1 }} />
        {[2, 3, 5, 8].map((w) => (
          <Pressable
            key={w}
            testID={`width-${w}`}
            onPress={() => setWidth(w)}
            style={[styles.widthChip, width === w && styles.widthChipActive]}
          >
            <View style={{ width: w * 2, height: w, borderRadius: w, backgroundColor: colors.onSurface }} />
          </Pressable>
        ))}
      </View>

      <View
        style={[styles.canvas, { height }]}
        {...responder.panHandlers}
        testID="canvas-surface"
      >
        <Svg width="100%" height="100%" viewBox="0 0 200 500" preserveAspectRatio="xMidYMid meet">
          <G stroke={colors.borderStrong} strokeWidth={1} fill="none">
            {MANNEQUIN[gender].map((d, i) => (
              <Path key={`m-${i}`} d={d} />
            ))}
          </G>
        </Svg>
        <Svg style={StyleSheet.absoluteFill} pointerEvents="none">
          {strokes.map((s, i) => (
            <Path key={`s-${i}`} d={s.d} stroke={s.color} strokeWidth={s.width} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          ))}
          {current ? (
            <Path d={current} stroke={color} strokeWidth={width} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          ) : null}
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: colors.surfaceSecondary },
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

  palette: { flexDirection: "row", alignItems: "center", gap: 6, padding: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderColor: colors.border },
  colorChip: { width: 22, height: 22, borderRadius: 11, borderWidth: 1 },
  colorChipActive: { transform: [{ scale: 1.15 }], borderWidth: 2, borderColor: colors.onSurface },
  widthChip: { padding: 6, borderWidth: 1, borderColor: colors.border, minWidth: 28, alignItems: "center", justifyContent: "center" },
  widthChipActive: { borderColor: colors.brand },

  canvas: { backgroundColor: colors.surface },
});
