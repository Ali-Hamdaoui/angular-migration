'use client';

import { useEffect, useState } from 'react';
import { getProductionPreflight } from '@/api/preflights';
import { G01ReviewPanel } from '@/components/G01ReviewPanel';
import type { ProductionPreflight } from '@/types/preflight';
import styles from './PreflightReviewPage.module.css';

export default function PreflightReviewPage({ params }: { params: Promise<{ preflightId: string }> }) {
  const [preflight, setPreflight] = useState<ProductionPreflight | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setPreflight(null);
    setError(null);
    void params
      .then(({ preflightId }) => getProductionPreflight(preflightId))
      .then((result) => { if (active) setPreflight(result); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Preflight could not be loaded.');
      });
    return () => { active = false; };
  }, [params]);

  if (error) return <main className={styles.state}><section role="alert"><p>Control tower</p><h1>G01 evidence is unavailable</h1><span>{error}</span></section></main>;
  if (!preflight) return <main className={styles.state}><section role="status"><p>Control tower</p><h1>Loading G01 evidence</h1><span>Connecting to the authoritative production preflight.</span></section></main>;
  return <G01ReviewPanel preflight={preflight} />;
}
