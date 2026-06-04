import Sidebar from "./Sidebar";

export default function AppShell({ page, onNavigate, children, userEmail, userTier }) {
  return (
    <div className="min-h-screen" style={{ background: "var(--bg-page)" }}>
      <Sidebar page={page} onNavigate={onNavigate} userEmail={userEmail} userTier={userTier} />
      <main
        style={{
          marginLeft: 240,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
        }}
      >
        {children}
      </main>
    </div>
  );
}
