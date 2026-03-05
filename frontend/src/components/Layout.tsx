import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";
import TopNav from "./TopNav";
import { refreshCurrentPrices } from "../api/client";

const PRICE_REFRESH_INTERVAL_MS = 60_000;

export default function Layout() {
  const location = useLocation();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Refresh prices on every page navigation
    refreshCurrentPrices().catch(() => {});
  }, [location.pathname]);

  useEffect(() => {
    // Poll every 60 seconds while the app is open
    intervalRef.current = setInterval(() => {
      refreshCurrentPrices().catch(() => {});
    }, PRICE_REFRESH_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ backgroundColor: "var(--bg-base)" }}>
      <TopNav />
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
