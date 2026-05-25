/**
 * Round 8 Agent J — Visual Smoke Test
 * Tests that App renders without crashing and nav-tabs are present.
 */
import { render } from "@testing-library/react";
import App from "../App";

// ── Mock axios (must be before App import) ──────────────────────────
jest.mock("axios", () => ({
  get: jest.fn(() => Promise.resolve({ data: [] })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
  patch: jest.fn(() => Promise.resolve({ data: {} })),
  create: jest.fn(function () { return jest.mocked(this); }),
  interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  defaults: { headers: { common: {} } },
}));

// ── Mock all child components to avoid cascade failures ─────────────
jest.mock("../components/GridHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/BarHeatmap", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/PatternCard", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/TrinityView", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/SidebarPanels", () => ({
  FlipZonesPanel: () => null, StackedNodesPanel: () => null, TugOfWarPanel: () => null,
  ScenarioPanel: () => null, RiskDashboardPanel: () => null, OpportunitiesPanel: () => null,
  ImpliedMovePanel: () => null, VolAnalyticsPanel: () => null, GreekReferencePanel: () => null,
  UsagePanel: () => null, LivePolicyPanel: () => null,
}));
jest.mock("../components/AdvancedAnalyticsPanel", () => ({
  MarketRegimePanel: () => null, ImpliedPDFPanel: () => null, HedgeImpulsePanel: () => null,
  PressureCloudPanel: () => null, CharmIntegralPanel: () => null,
}));
jest.mock("../components/PortfolioPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/FlowTicker", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/HistoryPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/OptionsChainTable", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/MultiTimeframeGEXPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/AlertsPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/UOAPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/heatseeker/HeatseekerDashboard", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/AlertOverlay", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/PWAInstallBanner", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/SettingsPanel", () => ({ SettingsPanel: () => null }));
jest.mock("../components/ShortcutsModal", () => ({ ShortcutsModal: () => null }));
jest.mock("../components/MorningBriefing", () => ({ MorningBriefing: () => null }));
jest.mock("../components/PositionSizing", () => ({ PositionSizing: () => null }));
jest.mock("../components/TradeEntry", () => ({ TradeEntry: () => null }));
jest.mock("../components/TradeJournal", () => ({ TradeJournal: () => null }));
jest.mock("../components/DashboardSummary", () => ({ DashboardSummary: () => null }));
jest.mock("../components/TradeAnalytics", () => ({ TradeAnalytics: () => null }));
jest.mock("../components/SocialFlowPanel", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/ToxicityGauge", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/VannaChart", () => ({ __esModule: true, default: () => null }));
jest.mock("../components/ErrorBoundary", () => ({ __esModule: true, default: ({ children }) => children }));
jest.mock("../components/RetryButton", () => ({ RetryButton: () => null, ErrorState: () => null }));
jest.mock("../hooks/useWebSocketGex", () => ({ useWebSocketGex: () => ({ readyState: 0, lastMessage: null }) }));
jest.mock("../hooks/useDebounce", () => ({ useDebounce: (val) => val }));
jest.mock("../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: jest.fn() }),
  ThemeProvider: ({ children }) => children,
}));
jest.mock("../utils/dataDecimator", () => ({ autoDecimate: (data) => data }));

// ── Tests ───────────────────────────────────────────────────────────
describe("Visual Smoke Test — Tab Render", () => {
  test("renders App default (trinity tab) without crash", () => {
    const { container } = render(<App />);
    expect(container.querySelector(".nav-tabs")).toBeInTheDocument();
  });

  test("renders nav-tabs with 6 tab buttons", () => {
    const { container } = render(<App />);
    const tabs = container.querySelectorAll(".nav-tabs .btn");
    expect(tabs.length).toBeGreaterThanOrEqual(6);
  });

  test.each(["trinity", "heatseeker", "skylit", "portfolio", "journal", "swarmspx"])(
    "nav-tabs contains %s button", (tab) => {
      const { container } = render(<App />);
      const tabButtons = Array.from(container.querySelectorAll(".nav-tabs .btn"));
      const found = tabButtons.some((btn) => btn.textContent.toLowerCase() === tab);
      expect(found).toBe(true);
    }
  );

  test("App renders root element", () => {
    const { container } = render(<App />);
    expect(container.firstChild).toBeTruthy();
  });

  test("no duplicate mount errors", () => {
    const { unmount } = render(<App />);
    expect(() => unmount()).not.toThrow();
  });
});
