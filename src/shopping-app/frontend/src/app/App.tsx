import { useState } from "react";
import { SearchList } from "./SearchList";
import { SearchDetail } from "./SearchDetail";

export function App() {
  const [view, setView] = useState<"list" | "detail">("list");
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);

  const openSearch = (id: string) => {
    setActiveSearchId(id);
    setView("detail");
  };

  const goHome = () => {
    setView("list");
    setActiveSearchId(null);
  };

  return (
    <div className="app">
      {view === "list" ? (
        <SearchList onOpenSearch={openSearch} />
      ) : (
        <SearchDetail searchId={activeSearchId!} onBack={goHome} />
      )}
    </div>
  );
}
