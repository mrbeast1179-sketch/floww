import React, { useState, useMemo } from "react";
import { useFlowseeker } from "../../hooks/useFlowseeker";
import FlowFilters from "./FlowFilters";
import FlowTable from "./FlowTable";
import FlowDrilldown from "./FlowDrilldown";
import FlowTicker from "../FlowTicker";

export default function FlowseekerTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [minPremium, setMinPremium] = useState(0);
  const [classFilter, setClassFilter] = useState("all");
  const [selected, setSelected] = useState(null);

  const { data, loading, error, refresh } = useFlowseeker("live", {
    ticker,
    min_premium: minPremium,
    limit: 200,
    refreshMs: 5000,
    skip: !active,
  });

  const filterValue = useMemo(
    () => ({ ticker, classification: classFilter, minPremium }),
    [ticker, classFilter, minPremium]
  );

  const prints = useMemo(() => {
    const all = data?.prints || [];
    if (classFilter === "all") return all;
    return all.filter((p) => p.classification === classFilter);
  }, [data, classFilter]);

  const handleFilterChange = (patch) => {
    if ("ticker" in patch) setTicker(patch.ticker);
    if ("classification" in patch) setClassFilter(patch.classification);
    if ("minPremium" in patch) setMinPremium(patch.minPremium);
  };

  return (
    <div className="p-3 space-y-3">
      {/* Header with filters + refresh */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FlowFilters value={filterValue} onChange={handleFilterChange} />
        <button className="btn" onClick={refresh}>
          Refresh
        </button>
      </div>

      {/* Flow Table */}
      <FlowTable
        prints={prints}
        loading={loading}
        error={error?.toString() || null}
        onSelect={setSelected}
      />

      {/* Live Tape sub-panel */}
      <div className="panel p-3">
        <div className="label mb-2">Live Tape</div>
        <FlowTicker ticker={ticker} />
      </div>

      {/* FlowDrilldown modal */}
      {selected && (
        <FlowDrilldown
          symbol={selected.ticker || ticker}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
