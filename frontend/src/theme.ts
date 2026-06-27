export const colors = {
  surface: "#FDFBF7",
  onSurface: "#1A1918",
  surfaceSecondary: "#F5F2EB",
  onSurfaceSecondary: "#4A4845",
  surfaceTertiary: "#EAE5DA",
  onSurfaceTertiary: "#6B6761",
  surfaceInverse: "#1A1918",
  onSurfaceInverse: "#FDFBF7",
  brand: "#A3523B",
  brandPrimary: "#A3523B",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#C97A63",
  brandTertiary: "#F2E2DC",
  onBrandTertiary: "#6B2A17",
  success: "#5C6B5D",
  warning: "#B38A58",
  error: "#A3523B",
  info: "#8C8984",
  border: "#EAE5DA",
  borderStrong: "#CFC8BB",
  divider: "#EAE5DA",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radii = { sm: 0, md: 4, lg: 8, pill: 999 };

export const MODES = [
  { key: "design_call", label: "Design Call", color: "#A3523B", emoji: "•" },
  { key: "measurement_call", label: "Measurement Call", color: "#B38A58", emoji: "•" },
  { key: "sending_pieces", label: "Sending Pieces", color: "#5C6B5D", emoji: "•" },
  { key: "personal", label: "Personal", color: "#8C8984", emoji: "•" },
] as const;

export type ModeKey = (typeof MODES)[number]["key"];
export const modeColor = (k: string) => MODES.find((m) => m.key === k)?.color ?? colors.info;
export const modeLabel = (k: string) => MODES.find((m) => m.key === k)?.label ?? k;

export const fonts = {
  serif: "Georgia",
  sans: "System",
};
