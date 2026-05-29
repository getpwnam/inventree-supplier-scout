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
  Title
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { useMemo, useState } from 'react';
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
  default_query?: string;
  part_pk: number;
  suppliers: Supplier[];
  top_n?: number;
  show_score?: boolean;
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
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());

  const supplierOptions = useMemo(
    () => suppliers.map((s) => ({ label: s.name, value: String(s.pk) })),
    [suppliers]
  );

  const selectedCandidates = useMemo(() => {
    return candidates.filter((candidate) =>
      selectedSkus.has(String(candidate.supplier_part_number || ''))
    );
  }, [candidates, selectedSkus]);

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
                          <>{candidate.supplier_part_number || ''}</>
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
