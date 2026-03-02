import { Outlet } from "react-router-dom";
import TopNav from "./TopNav";

export default function Layout() {
  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ backgroundColor: "var(--bg-base)" }}>
      <TopNav />
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
