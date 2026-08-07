export const SIDEBAR_KEY = "apw.sidebarCollapsed";

// legacy:true tabs render inside a .legacy-theme wrapper (preserved look)
// These are the pages we keep from the original floww project
// The original floww Confluence Decoder views — AlphaPod clone removed 2026-06-15.
export const NAV_ITEMS = [
  // Decoder
  { id: "heatseeker", label: "Heatseeker", group: "Decoder", icon: "grid", legacy: true },
  { id: "trinity",    label: "Trinity",    group: "Decoder", icon: "layers", legacy: true },
  { id: "flowseeker-pro", label: "Flowseeker Pro", group: "Decoder", icon: "zap", legacy: true },
  { id: "steal-three", label: "Steal Three", group: "Decoder", icon: "sparkles", badge: "NEW" },

  // Trading
  { id: "portfolio",  label: "Portfolio",  group: "Trading", icon: "trending-up" },
  { id: "journal",    label: "Journal",    group: "Trading", icon: "list" },
  { id: "swarmspx",   label: "SwarmSPX",   group: "Trading", icon: "sparkles" },
  { id: "turboquant", label: "turboQuantDC", group: "Trading", icon: "cpu" },
];

export const LEGACY_PAGES = new Set(NAV_ITEMS.filter(i => i.legacy).map(i => i.id));

// Map page id to display name for breadcrumb/header
export const PAGE_NAMES = {};
NAV_ITEMS.forEach(item => { PAGE_NAMES[item.id] = item.label; });
