import React, { useEffect, useMemo, useState } from 'react';
import { InfoCard, Progress, ResponseErrorPanel } from '@backstage/core-components';
import { fetchApiRef, useApi } from '@backstage/core-plugin-api';

export type DskPlanSummary = {
  create: number;
  update: number;
  delete: number;
  conflict: number;
  noop: number;
};

export type DskPlanCardProps = {
  title?: string;
  manifestPath?: string;
  endpoint?: string;
};

type DskPlanResponse = {
  summary?: Partial<DskPlanSummary>;
};

type DskPlanState =
  | { status: 'loading'; summary?: never; error?: never }
  | { status: 'ready'; summary: DskPlanSummary; error?: never }
  | { status: 'error'; summary?: never; error: Error };

const emptySummary: DskPlanSummary = {
  create: 0,
  update: 0,
  delete: 0,
  conflict: 0,
  noop: 0,
};

const summaryLabels: Array<keyof DskPlanSummary> = [
  'create',
  'update',
  'delete',
  'conflict',
  'noop',
];

export const DskPlanCard = ({
  title = 'DSK Plan',
  manifestPath,
  endpoint = '/api/dsk/plan',
}: DskPlanCardProps) => {
  const fetchApi = useApi(fetchApiRef);
  const [state, setState] = useState<DskPlanState>({ status: 'loading' });

  const requestUrl = useMemo(() => {
    if (!manifestPath) {
      return endpoint;
    }
    const params = new URLSearchParams({ manifestPath });
    return `${endpoint}?${params.toString()}`;
  }, [endpoint, manifestPath]);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });

    fetchApi
      .fetch(requestUrl)
      .then(async response => {
        if (!response.ok) {
          throw new Error(`DSK plan request failed with status ${response.status}`);
        }
        return response.json() as Promise<DskPlanResponse>;
      })
      .then(plan => {
        if (cancelled) {
          return;
        }
        setState({
          status: 'ready',
          summary: {
            ...emptySummary,
            ...plan.summary,
          },
        });
      })
      .catch(error => {
        if (!cancelled) {
          setState({ status: 'error', error });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [fetchApi, requestUrl]);

  return (
    <InfoCard title={title}>
      {state.status === 'loading' && <Progress />}
      {state.status === 'error' && <ResponseErrorPanel error={state.error} />}
      {state.status === 'ready' && (
        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 16 }}>
          {summaryLabels.map(key => (
            <div key={key}>
              <dt style={{ textTransform: 'capitalize', fontSize: 12 }}>{key}</dt>
              <dd style={{ margin: 0, fontSize: 28, fontWeight: 600 }}>{state.summary[key]}</dd>
            </div>
          ))}
        </dl>
      )}
    </InfoCard>
  );
};
