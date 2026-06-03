export const SIDEBAR_KEY = "apw.sidebarCollapsed";
// legacy:true tabs render inside a .legacy-theme wrapper (preserved look)
export const NAV_ITEMS = [
  { id: "flow-alerts", label: "Flow Alerts", group: "Flow" },
  { id: "alpha-flow",  label: "Alpha Flow",  group: "Flow" },
  { id: "daily-report",label: "Daily Report",group: "Flow" },
  { id: "spx-gex",     label: "SPX GEX",     group: "SPX"  },
  { id: "trinity",     label: "Trinity",     group: "Legacy", legacy: true },
  { id: "heatseeker",  label: "Heatseeker",  group: "Legacy", legacy: true },
  { id: "skylit",      label: "Skylit",      group: "Legacy" },
  { id: "flowseeker",  label: "Flowseeker",  group: "Legacy" },
  { id: "portfolio",   label: "Portfolio",   group: "Legacy" },
  { id: "journal",     label: "Journal",     group: "Legacy" },
  { id: "swarmspx",    label: "SwarmSPX",    group: "Legacy" },
];
export const LEGACY_PAGES = new Set(NAV_ITEMS.filter(i => i.legacy).map(i => i.id));
