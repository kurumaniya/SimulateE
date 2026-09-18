import { Suspense } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { AuthGate } from "@/components/auth/AuthGate";

export default function LibraryLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <div className="flex h-dvh overflow-hidden">
        <div className="hidden md:block">
          <Suspense fallback={<div className="h-full w-60 border-r border-line bg-elevated" />}>
            <Sidebar />
          </Suspense>
        </div>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1600px] px-5 py-6 md:px-8 md:py-8">{children}</div>
        </main>
      </div>
    </AuthGate>
  );
}
