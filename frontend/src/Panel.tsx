import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Group,
  NativeSelect,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { useEffect, useMemo, useState } from 'react';
import { LocalizedComponent } from './locale';

type Supplier = {
  name: string;
  pk: number;
};

type Candidate = {
  supplier_part_number?: string;
  manufacturer_part_number?: string;
  description?: string;
  available_quantity?: number;
  unit_price?: number;
  score?: number;
  supplier_link?: string;
  existing_supplier_part?: boolean;
  action?: string;
};

type MatcherContext = {
  title?: string;
  search_url: string;
  apply_url: string;
  run_resync_url?: string;
  rate_status_url?: string;
  default_query?: string;
  part_pk: number;
  suppliers: Supplier[];
  top_n?: number;
  show_score?: boolean;
};

type SupplierRateStatus = {
  supplier_pk: number;
  supplier_key?: string;
  supplier_name?: string;
  configured?: boolean;
  rate_limit_per_second?: number;
  daily_limit?: number;
  daily_count?: number;
  daily_remaining?: number | null;
  daily_percent_used?: number;
  daily_reset_at?: string;
};

type ResyncResult = {
  scope?: 'supplier' | 'part';
  action?: 'resync' | 'reset_cursor';
  processed?: number;
  updated?: number;
  created?: number;
  skipped?: number;
  failed?: number;
  round_robin?: boolean;
  cursor_before?: number;
  cursor_after?: number;
};

function formatUnitPrice(value: unknown): string {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return numeric.toFixed(3);
  }

  return value == null ? '' : String(value);
}

function SupplierScoutMatcher({
  context,
  serverContext,
  onClose
}: {
  context: InvenTreePluginContext;
  serverContext: MatcherContext;
  onClose?: () => void;
}) {
  const suppliers = serverContext.suppliers || [];
  const [query, setQuery] = useState<string>(serverContext.default_query || '');
  const [supplier, setSupplier] = useState<string>(
    suppliers[0] ? String(suppliers[0].pk) : ''
  );
  const [minQty, setMinQty] = useState<string>('');
  const [maxQty, setMaxQty] = useState<string>('');
  const [showTokens, setShowTokens] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [isError, setIsError] = useState<boolean>(false);
  const [searching, setSearching] = useState<boolean>(false);
  const [applying, setApplying] = useState<boolean>(false);
  const [runningResync, setRunningResync] = useState<boolean>(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());
  const [rateStatus, setRateStatus] = useState<SupplierRateStatus | null>(null);
  const [loadingRateStatus, setLoadingRateStatus] = useState<boolean>(false);
  const [resyncResult, setResyncResult] = useState<ResyncResult | null>(null);

  const supplierOptions = useMemo(
    () => suppliers.map((s) => ({ label: s.name, value: String(s.pk) })),
    [suppliers]
  );

  const selectedCandidates = useMemo(() => {
    return candidates.filter((candidate) =>
      selectedSkus.has(String(candidate.supplier_part_number || ''))
    );
  }, [candidates, selectedSkus]);

  async function fetchRateStatus(supplierPk?: string) {
    if (!serverContext.rate_status_url) {
      return;
    }

    const supplierValue = Number(supplierPk || supplier);
    if (!Number.isFinite(supplierValue) || supplierValue <= 0) {
      return;
    }

    setLoadingRateStatus(true);

    try {
      const response = await context.api.get(
        `${serverContext.rate_status_url}?supplier=${supplierValue}`
      );
      const data = response?.data || {};
      const status = (data.suppliers || [])[0] || null;
      setRateStatus(status);
    } catch (error: any) {
      setRateStatus(null);
      setIsError(true);
      setStatusMessage(
        error?.response?.data?.message ||
          error?.message ||
          'Failed to load API usage status'
      );
    } finally {
      setLoadingRateStatus(false);
    }
  }

  useEffect(() => {
    fetchRateStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplier, serverContext.rate_status_url]);

  function renderRateBadge() {
    if (!rateStatus) {
      return (
        <Badge variant='light' color='gray'>
          API status unavailable
        </Badge>
      );
    }

    const dailyLimit = Number(rateStatus.daily_limit || 0);
    const dailyCount = Number(rateStatus.daily_count || 0);
    const dailyRemaining =
      rateStatus.daily_remaining == null
        ? null
        : Number(rateStatus.daily_remaining);

    let badgeColor: 'green' | 'yellow' | 'red' | 'blue' = 'blue';

    if (dailyLimit > 0) {
      const ratio = dailyCount / Math.max(1, dailyLimit);
      if (dailyRemaining === 0) {
        badgeColor = 'red';
      } else if (ratio >= 0.9) {
        badgeColor = 'yellow';
      } else {
        badgeColor = 'green';
      }
    }

    const dailyText =
      dailyLimit > 0
        ? `${dailyCount}/${dailyLimit} day (${dailyRemaining} left)`
        : `${dailyCount} day (unlimited)`;

    return (
      <Group gap='xs' align='center'>
        <Badge variant='light' color={badgeColor}>
          {dailyText}
        </Badge>
        <Badge variant='dot' color='blue'>
          {`${rateStatus.rate_limit_per_second || 0}/sec`}
        </Badge>
        {rateStatus.daily_reset_at && (
          <Text size='xs' c='dimmed'>
            Resets:{' '}
            {rateStatus.daily_reset_at.replace('T', ' ').replace('Z', ' UTC')}
          </Text>
        )}
        <Tooltip
          multiline
          w={260}
          label='Badge legend: green < 90% daily usage, yellow >= 90%, red = daily limit reached. Blue dot shows calls/sec limit.'
        >
          <Badge variant='outline' color='gray'>
            Legend
          </Badge>
        </Tooltip>
      </Group>
    );
  }

  async function runResync(scope: 'supplier' | 'part' | 'reset_cursor') {
    if (!serverContext.run_resync_url) {
      setIsError(true);
      setStatusMessage('Missing resync URL in plugin context');
      return;
    }

    setRunningResync(true);

    try {
      const payload: Record<string, number | string> = {
        supplier: Number(supplier)
      };

      if (scope === 'part') {
        payload.part_pk = Number(serverContext.part_pk);
      } else if (scope === 'reset_cursor') {
        payload.action = 'reset_cursor';
      }

      const response = await context.api.post(
        serverContext.run_resync_url,
        payload
      );
      const data = response?.data || {};

      if (data.message !== 'OK') {
        setIsError(true);
        setStatusMessage(data.message || 'Manual resync failed');
        return;
      }

      let summary = '';
      if (scope === 'reset_cursor') {
        summary = `Resync cursor reset: ${data.cursor_before ?? 0} -> ${data.cursor_after ?? 0}`;
      } else {
        summary = `Resync (${scope}) processed=${data.processed || 0}, updated=${data.updated || 0}, created=${data.created || 0}, skipped=${data.skipped || 0}, failed=${data.failed || 0}`;
      }

      setResyncResult(data as ResyncResult);

      setIsError((data.failed || 0) > 0);
      setStatusMessage(summary);

      notifications.show({
        title: 'Supplier Scout',
        message: summary,
        color: (data.failed || 0) > 0 ? 'yellow' : 'green'
      });

      await fetchRateStatus();
    } catch (error: any) {
      setIsError(true);
      setStatusMessage(
        error?.response?.data?.message ||
          error?.message ||
          'Manual resync failed'
      );
    } finally {
      setRunningResync(false);
    }
  }

  async function searchMatches() {
    if (!serverContext.search_url) {
      setIsError(true);
      setStatusMessage('Missing candidate search URL in plugin context');
      return;
    }

    setSearching(true);
    setCandidates([]);
    setSelectedSkus(new Set());

    try {
      const payload = {
        pk: serverContext.part_pk,
        supplier: Number(supplier),
        query: query.trim(),
        top_n: serverContext.top_n || 10,
        ...(minQty && { min_qty: Number(minQty) }),
        ...(maxQty && { max_qty: Number(maxQty) })
      };

      const response = await context.api.post(
        serverContext.search_url,
        payload
      );
      const data = response?.data || {};

      const foundCandidates: Candidate[] = data.candidates || [];
      setCandidates(foundCandidates);

      if (foundCandidates.length === 0) {
        setIsError(true);
        setStatusMessage(data.message || 'No supplier matches returned');
      } else {
        setIsError(false);
        setStatusMessage(
          `Found ${foundCandidates.length} candidate(s) for query: ${data.query}`
        );
      }
    } catch (error: any) {
      setIsError(true);
      setStatusMessage(
        error?.response?.data?.message ||
          error?.message ||
          'Candidate search failed'
      );
    } finally {
      setSearching(false);
    }
  }

  async function applySelection() {
    if (!serverContext.apply_url) {
      setIsError(true);
      setStatusMessage('Missing candidate apply URL in plugin context');
      return;
    }

    if (selectedCandidates.length === 0) {
      setIsError(true);
      setStatusMessage('Select at least one candidate to apply');
      return;
    }

    setApplying(true);

    try {
      const payload = {
        pk: serverContext.part_pk,
        supplier: Number(supplier),
        candidates: selectedCandidates
      };

      const response = await context.api.post(serverContext.apply_url, payload);
      const data = response?.data || {};

      if (data.message !== 'OK') {
        setIsError(true);
        setStatusMessage(data.message || 'Apply candidates failed');
        return;
      }

      const summary = `Applied candidates: created=${data.created || 0}, updated=${data.updated || 0}, errors=${data.errors || 0}`;
      setIsError((data.errors || 0) > 0);
      setStatusMessage(summary);

      notifications.show({
        title: 'Supplier Scout',
        message: summary,
        color: (data.errors || 0) > 0 ? 'yellow' : 'green'
      });

      setSelectedSkus(new Set());
      context.reloadContent?.();
    } catch (error: any) {
      setIsError(true);
      setStatusMessage(
        error?.response?.data?.message ||
          error?.message ||
          'Apply candidates failed'
      );
    } finally {
      setApplying(false);
    }
  }

  function toggleSelection(candidate: Candidate, checked: boolean) {
    const sku = String(candidate.supplier_part_number || '');
    setSelectedSkus((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(sku);
      } else {
        next.delete(sku);
      }
      return next;
    });
  }

  return (
    <Stack gap='sm'>
      <Text c='dimmed' size='sm'>
        Search supplier matches, select candidates, then create or update
        supplier parts.
      </Text>

      {statusMessage && (
        <Alert color={isError ? 'red' : 'green'}>{statusMessage}</Alert>
      )}

      <Group align='end' grow>
        <NativeSelect
          label='Supplier'
          data={supplierOptions}
          value={supplier}
          onChange={(event) => setSupplier(event.currentTarget.value)}
        />
        <Button onClick={searchMatches} loading={searching}>
          Find Matches
        </Button>
      </Group>

      <Paper withBorder p='xs' radius='md'>
        <Stack gap='xs'>
          <Text size='sm' fw={600}>
            API Usage
          </Text>
          {renderRateBadge()}
          <Group gap='xs'>
            <Button
              variant='subtle'
              size='xs'
              onClick={() => fetchRateStatus()}
              loading={loadingRateStatus}
            >
              Refresh API Usage
            </Button>
            <Button
              variant='light'
              size='xs'
              onClick={() => runResync('part')}
              loading={runningResync}
            >
              Resync This Part
            </Button>
            <Button
              variant='light'
              size='xs'
              onClick={() => runResync('supplier')}
              loading={runningResync}
            >
              Resync Supplier Batch
            </Button>
            <Tooltip label='Admin only: reset supplier round-robin cursor to first supplier part'>
              <Button
                variant='outline'
                color='orange'
                size='xs'
                onClick={() => runResync('reset_cursor')}
                loading={runningResync}
              >
                Reset Supplier Cursor
              </Button>
            </Tooltip>
          </Group>
        </Stack>
      </Paper>

      {resyncResult && (
        <Paper withBorder p='xs' radius='md'>
          <Group justify='space-between'>
            <Text size='sm' fw={600}>
              Latest Resync
            </Text>
            <Text size='xs' c='dimmed'>
              Scope: {resyncResult.scope || '-'}
            </Text>
          </Group>
          <Text size='sm'>
            {resyncResult.action === 'reset_cursor'
              ? `Cursor reset ${resyncResult.cursor_before ?? 0} -> ${resyncResult.cursor_after ?? 0}`
              : `Cursor ${resyncResult.cursor_before ?? 0} -> ${resyncResult.cursor_after ?? 0} (${resyncResult.round_robin ? 'round-robin' : 'manual'})`}
          </Text>
        </Paper>
      )}

      {showTokens && (
        <Paper withBorder p='md' radius='md' mb='md'>
          <Stack gap='xs'>
            <Text size='sm' fw={600}>
              Search Query Tokens
            </Text>
            <Text size='xs' c='dimmed'>
              Edit the search query below. Leave blank to auto-generate from
              part data.
            </Text>
            <Textarea
              label='Search Query'
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder='Enter search terms separated by spaces, or leave blank for auto-generated query'
              minRows={3}
              maxRows={6}
            />
          </Stack>
        </Paper>
      )}

      <Button
        variant='subtle'
        size='xs'
        onClick={() => setShowTokens(!showTokens)}
        mb='sm'
      >
        {showTokens ? 'Hide' : 'Show'} Search Query
      </Button>

      <Group grow>
        <TextInput
          label='Min Quantity (optional)'
          value={minQty}
          onChange={(event) => setMinQty(event.currentTarget.value)}
          placeholder='Minimum order quantity'
          type='number'
        />
        <TextInput
          label='Max Quantity (optional)'
          value={maxQty}
          onChange={(event) => setMaxQty(event.currentTarget.value)}
          placeholder='Maximum preferred quantity'
          type='number'
        />
      </Group>

      <Paper withBorder p='sm' radius='md'>
        {candidates.length === 0 ? (
          <Text c='dimmed' size='sm'>
            No candidates loaded yet.
          </Text>
        ) : (
          <ScrollArea>
            <Table striped withTableBorder highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Select</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>SKU</Table.Th>
                  <Table.Th>Description</Table.Th>
                  <Table.Th>Available</Table.Th>
                  <Table.Th>Unit Price</Table.Th>
                  {serverContext.show_score === true && (
                    <Table.Th>Score</Table.Th>
                  )}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {candidates.map((candidate) => {
                  const sku = String(candidate.supplier_part_number || '');
                  const selected = selectedSkus.has(sku);
                  const isExisting = candidate.existing_supplier_part === true;

                  return (
                    <Table.Tr
                      key={
                        sku ||
                        `${candidate.manufacturer_part_number}-${candidate.description}`
                      }
                    >
                      <Table.Td>
                        <Checkbox
                          checked={selected}
                          onChange={(event) =>
                            toggleSelection(
                              candidate,
                              event.currentTarget.checked
                            )
                          }
                        />
                      </Table.Td>
                      <Table.Td>
                        <Badge
                          color={isExisting ? 'blue' : 'gray'}
                          variant='light'
                        >
                          {isExisting ? 'Existing (update)' : 'New (create)'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {candidate.supplier_link ? (
                          <Anchor
                            href={candidate.supplier_link}
                            target='_blank'
                            rel='noopener noreferrer'
                          >
                            {candidate.supplier_part_number || ''}
                          </Anchor>
                        ) : (
                          candidate.supplier_part_number || ''
                        )}
                      </Table.Td>
                      <Table.Td>{candidate.description || ''}</Table.Td>
                      <Table.Td>{candidate.available_quantity ?? ''}</Table.Td>
                      <Table.Td>
                        {formatUnitPrice(candidate.unit_price)}
                      </Table.Td>
                      {serverContext.show_score === true && (
                        <Table.Td>{candidate.score ?? ''}</Table.Td>
                      )}
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Paper>

      <Group justify='flex-end'>
        {onClose && (
          <Button variant='default' onClick={onClose}>
            Cancel
          </Button>
        )}
        <Button
          onClick={applySelection}
          loading={applying}
          disabled={selectedCandidates.length === 0 || applying}
        >
          Add / Update Selected
        </Button>
      </Group>
    </Stack>
  );
}

function SupplierScoutPanel({ context }: { context: InvenTreePluginContext }) {
  const serverContext = useMemo(() => {
    return (context.instance || {}) as MatcherContext;
  }, [context.instance]);

  return (
    <Stack gap='sm'>
      <Title order={4}>Supplier Part Matching</Title>
      <SupplierScoutMatcher context={context} serverContext={serverContext} />
    </Stack>
  );
}

export function renderSupplierScoutPanel(context: InvenTreePluginContext) {
  checkPluginVersion(context);

  return (
    <LocalizedComponent locale={context.locale}>
      <SupplierScoutPanel context={context} />
    </LocalizedComponent>
  );
}

export function getFeature({
  serverContext,
  inventreeContext
}: {
  serverContext: MatcherContext;
  inventreeContext: InvenTreePluginContext;
}) {
  modals.open({
    title: serverContext?.title || 'Supplier Part Matching',
    size: '90%',
    children: (
      <LocalizedComponent locale={inventreeContext.locale}>
        <SupplierScoutMatcher
          context={inventreeContext}
          serverContext={serverContext}
          onClose={() => modals.closeAll()}
        />
      </LocalizedComponent>
    )
  });
}
