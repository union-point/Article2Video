export const tokens = {
  themes: {
    paper: {
      background: "#E9E8F2",
      ink: "#242139",
      accent: "#4739C7",
      surface: "#FAF9FF",
      muted: "#625D76",
      signal: "#B9E7D5",
    },
    slate: {
      background: "#242139",
      ink: "#FAF9FF",
      accent: "#C3BAFF",
      surface: "#353149",
      muted: "#B9B4CB",
      signal: "#B9E7D5",
    },
  },
  fonts: { display: "Arial", body: "Arial" },
  inset: 80,
  gap: 28,
  radius: 12,
  minText: 36,
  motion: { calm: 24, brisk: 14 },
} as const;
