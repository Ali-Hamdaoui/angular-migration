"use client";

import { useEffect, useState } from "react";
import { getProductionPreflight } from "@/api/preflights";
import { G01ReviewPanel } from "@/components/G01ReviewPanel";
import type { ProductionPreflight } from "@/types/preflight";

export default function PreflightReviewPage({ params }: { params: Promise<{ preflightId: string }> }) {
  const [preflight, setPreflight] = useState<ProductionPreflight | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    params.then(({ preflightId }) => getProductionPreflight(preflightId).then(setPreflight).catch(() => setError("Preflight could not be loaded.")));
  }, [params]);

  if (error) return <main><p>{error}</p></main>;
  if (!preflight) return <main><p>Loading G01 evidence…</p></main>;
  return <main><G01ReviewPanel preflight={preflight} /></main>;
}
