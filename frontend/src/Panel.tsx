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
  Collapse,
  Group,
  Loader,
  MultiSelect,
  NativeSelect,
  Paper,
  Pill,
  ScrollArea,
  Stack,
  Table,
  TagsInput,
  Text,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton
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
  manufacturer_name?: string;
  manufacturer_part_number?: string;
  description?: string;
  available_quantity?: number;
  unit_price?: number;
  score?: number;
  supplier_link?: string;
  existing_supplier_part?: boolean;
  action?: string;
  _supplier_pk?: number;
  _supplier_name?: string;
};

type MatcherContext = {
  title?: string;
  search_url: string;
  apply_url: string;
  run_resync_url?: string;
  rate_status_url?: string;
  token_debug_url?: string;
  default_query?: string;
  default_min_qty?: number;
  default_max_qty?: number | null;
  part_pk: number;
  suppliers: Supplier[];
  top_n?: number;
  show_score?: boolean;
};

type TokenSourceEntry = {
  source: string;
  value?: string;
  tokens?: string[];
};

type TokenGroups = {
  nameValues: string[];
  nameTokens: string[];
  categoryTokens: string[];
  parameterTokens: string[];
  manufacturerPartTokens: string[];
  semanticTokens: string[];
};

type TokenCheckboxState = {
  includePartName: boolean;
  includePartNameTokens: boolean;
  includeCategoryTokens: boolean;
  includeParameterTokens: boolean;
  includeManufacturerPartTokens: boolean;
  includeSemanticTokens: boolean;
};

type ResultColumnKey =
  | 'supplier'
  | 'sku'
  | 'mpn'
  | 'description'
  | 'available'
  | 'unitPrice'
  | 'score';

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

type TokenPillSource =
  | 'part-name'
  | 'name-token'
  | 'category'
  | 'parameter'
  | 'manufacturer-part'
  | 'ipn'
  | 'sku'
  | 'semantic'
  | 'manual';

const TOKEN_PILL_META: Record<
  TokenPillSource,
  { label: string; color: string }
> = {
  'part-name': { label: 'Part name', color: 'pink' },
  'name-token': { label: 'Name token', color: 'yellow' },
  category: { label: 'Category', color: 'blue' },
  parameter: { label: 'Parameter', color: 'teal' },
  'manufacturer-part': { label: 'Manufacturer part', color: 'red' },
  ipn: { label: 'IPN', color: 'violet' },
  sku: { label: 'SKU', color: 'orange' },
  semantic: { label: 'Semantic hint', color: 'cyan' },
  manual: { label: 'Manual / other', color: 'gray' }
};

const TOKEN_PILL_PRIORITY: Record<TokenPillSource, number> = {
  'manufacturer-part': 80,
  ipn: 75,
  sku: 70,
  parameter: 65,
  category: 60,
  'part-name': 55,
  'name-token': 50,
  semantic: 30,
  manual: 10
};

const QUERY_SOURCE_TO_PILL_SOURCE: Record<string, TokenPillSource> = {
  manufacturer_part: 'manufacturer-part',
  IPN: 'ipn',
  SKU: 'sku',
  parameter: 'parameter',
  category: 'category',
  name: 'name-token',
  description: 'name-token'
};

function normalizeTokenKey(token: string): string {
  return String(token || '')
    .trim()
    .toLowerCase();
}

function setTokenSource(
  sourceByToken: Record<string, TokenPillSource>,
  token: string,
  source: TokenPillSource
) {
  const key = normalizeTokenKey(token);
  if (!key) {
    return;
  }

  const existing = sourceByToken[key];
  if (
    !existing ||
    TOKEN_PILL_PRIORITY[source] > TOKEN_PILL_PRIORITY[existing]
  ) {
    sourceByToken[key] = source;
  }
}

function getPillSourceForTag(
  tag: string,
  sourceByToken: Record<string, TokenPillSource>
): TokenPillSource {
  return sourceByToken[normalizeTokenKey(tag)] || 'manual';
}

function deriveNameTokensFromValues(values: string[]): string[] {
  const seen = new Set<string>();
  const tokens: string[] = [];

  for (const value of values) {
    const parts = String(value || '')
      .split(/[^A-Za-z0-9]+/)
      .map((part) => part.trim())
      .filter((part) => part.length >= 2);

    for (const part of parts) {
      const key = part.toLowerCase();
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      tokens.push(part);
    }
  }

  return tokens;
}

function formatUnitPrice(value: unknown): string {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return numeric.toFixed(3);
  }

  return value == null ? '' : String(value);
}

function formatDynamicColumnLabel(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDynamicColumnValue(value: unknown): string {
  if (value == null) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const DYNAMIC_COLUMN_EXCLUDED_FIELDS = new Set<string>([
  'supplier_part_number',
  'manufacturer_part_number',
  'description',
  'available_quantity',
  'unit_price',
  'score',
  'supplier_link',
  'existing_supplier_part',
  'existing_supplier_part_pk',
  'action',
  'price_breaks',
  'datasheet_url',
  'spec_attributes'
]);

function SupplierScoutMatcher({
  context,
  serverContext,
  onClose,
  modalId
}: {
  context: InvenTreePluginContext;
  serverContext: MatcherContext;
  onClose?: () => void;
  modalId?: string;
}) {
  const suppliers = serverContext.suppliers || [];
  const [queryTags, setQueryTags] = useState<string[]>(() =>
    dedupTokens(
      (serverContext.default_query || '')
        .split(/\s+/)
        .filter((t) => t.trim().length > 0)
    )
  );
  const [supplier, setSupplier] = useState<string>('');
  const [minQty, setMinQty] = useState<string>('');
  const [maxQty, setMaxQty] = useState<string>('');
  const [showTokens, setShowTokens] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [isError, setIsError] = useState<boolean>(false);
  const [searching, setSearching] = useState<boolean>(false);
  const [applying, setApplying] = useState<boolean>(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [hasExpandedModal, setHasExpandedModal] = useState<boolean>(false);
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());
  const [selectedDynamicColumns, setSelectedDynamicColumns] = useState<
    string[]
  >([]);
  const [visibleColumns, setVisibleColumns] = useState<
    Record<ResultColumnKey, boolean>
  >({
    supplier: true,
    sku: true,
    mpn: false,
    description: true,
    available: true,
    unitPrice: true,
    score: serverContext.show_score === true
  });
  const [rateStatus, setRateStatus] = useState<SupplierRateStatus | null>(null);
  const [rateStatuses, setRateStatuses] = useState<SupplierRateStatus[]>([]);
  const [loadingRateStatus, setLoadingRateStatus] = useState<boolean>(false);
  const [showApiUsage, setShowApiUsage] = useState<boolean>(false);

  // Token debug state
  const [tokenGroups, setTokenGroups] = useState<TokenGroups | null>(null);
  const [tokenDebugFetched, setTokenDebugFetched] = useState<boolean>(false);
  const [loadingTokens, setLoadingTokens] = useState<boolean>(false);
  const [tagSourceByToken, setTagSourceByToken] = useState<
    Record<string, TokenPillSource>
  >({});
  const [includePartName, setIncludePartName] = useState<boolean>(true);
  const [includePartNameTokens, setIncludePartNameTokens] =
    useState<boolean>(true);
  const [includeCategoryTokens, setIncludeCategoryTokens] =
    useState<boolean>(false);
  const [includeParameterTokens, setIncludeParameterTokens] =
    useState<boolean>(false);
  const [includeManufacturerPartTokens, setIncludeManufacturerPartTokens] =
    useState<boolean>(true);
  const [includeSemanticTokens, setIncludeSemanticTokens] =
    useState<boolean>(true);

  const supplierOptions = useMemo(
    () => [
      { label: 'All Supported', value: '' },
      ...suppliers.map((s) => ({ label: s.name, value: String(s.pk) }))
    ],
    [suppliers]
  );

  const tokenDebugUrl = useMemo(() => {
    if (serverContext.token_debug_url) {
      return serverContext.token_debug_url;
    }

    const searchUrl = String(serverContext.search_url || '').trim();
    if (!searchUrl) {
      return '';
    }

    return searchUrl.replace(/searchcandidates(?:\.(json))?$/, 'tokendebug$1');
  }, [serverContext.search_url, serverContext.token_debug_url]);

  const defaultMinQty = useMemo(() => {
    const value = Number(serverContext.default_min_qty);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  }, [serverContext.default_min_qty]);

  const defaultMaxQty = useMemo(() => {
    const value = Number(serverContext.default_max_qty);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  }, [serverContext.default_max_qty]);

  const minQtyPlaceholder = defaultMinQty
    ? `Min order qty (default ${defaultMinQty})`
    : 'Min order qty';
  const maxQtyPlaceholder = defaultMaxQty
    ? `Max preferred qty (default ${defaultMaxQty})`
    : 'Max preferred qty';

  const selectedCandidates = useMemo(() => {
    return candidates.filter((candidate) =>
      selectedSkus.has(String(candidate.supplier_part_number || ''))
    );
  }, [candidates, selectedSkus]);

  const activeTokenPillSources = useMemo(() => {
    const sources = new Set<TokenPillSource>();

    for (const tag of queryTags) {
      sources.add(getPillSourceForTag(tag, tagSourceByToken));
    }

    return Array.from(sources).sort(
      (left, right) => TOKEN_PILL_PRIORITY[right] - TOKEN_PILL_PRIORITY[left]
    );
  }, [queryTags, tagSourceByToken]);

  const activeRateStatuses = useMemo(
    () => rateStatuses.filter((status) => status.configured !== false),
    [rateStatuses]
  );

  const allSuppliersSelected = supplier === '';

  const availableDynamicColumns = useMemo(() => {
    const labels = new Map<string, string>();
    const counts = new Map<string, number>();

    for (const candidate of candidates) {
      const candidateRecord = candidate as Record<string, unknown>;

      for (const [fieldName, fieldValue] of Object.entries(candidateRecord)) {
        if (fieldName === 'spec_attributes') {
          if (
            fieldValue &&
            typeof fieldValue === 'object' &&
            !Array.isArray(fieldValue)
          ) {
            const specRecord = fieldValue as Record<string, unknown>;

            for (const [specName, specValue] of Object.entries(specRecord)) {
              const textValue = formatDynamicColumnValue(specValue).trim();
              if (!textValue) {
                continue;
              }

              const key = `spec:${specName}`;
              labels.set(key, specName);
              counts.set(key, (counts.get(key) || 0) + 1);
            }
          }

          continue;
        }

        if (
          DYNAMIC_COLUMN_EXCLUDED_FIELDS.has(fieldName) ||
          fieldName.startsWith('_')
        ) {
          continue;
        }

        const textValue = formatDynamicColumnValue(fieldValue).trim();
        if (!textValue) {
          continue;
        }

        const key = `field:${fieldName}`;
        labels.set(key, formatDynamicColumnLabel(fieldName));
        counts.set(key, (counts.get(key) || 0) + 1);
      }
    }

    return Array.from(labels.entries())
      .sort((left, right) => {
        const leftCount = counts.get(left[0]) || 0;
        const rightCount = counts.get(right[0]) || 0;

        if (rightCount !== leftCount) {
          return rightCount - leftCount;
        }

        return left[1].localeCompare(right[1]);
      })
      .map(([value, label]) => ({
        value,
        label
      }));
  }, [candidates]);

  const dynamicColumnLabelByKey = useMemo(
    () =>
      Object.fromEntries(
        availableDynamicColumns.map((column) => [column.value, column.label])
      ) as Record<string, string>,
    [availableDynamicColumns]
  );

  useEffect(() => {
    const availableKeys = new Set(
      availableDynamicColumns.map((column) => column.value)
    );

    setSelectedDynamicColumns((previous) =>
      previous.filter((columnKey) => availableKeys.has(columnKey))
    );
  }, [availableDynamicColumns]);

  function getDynamicColumnCellValue(candidate: Candidate, columnKey: string) {
    if (columnKey.startsWith('spec:')) {
      const specName = columnKey.slice(5);
      const specRecord = ((candidate as Record<string, unknown>)
        .spec_attributes || {}) as Record<string, unknown>;
      return formatDynamicColumnValue(specRecord[specName]);
    }

    if (columnKey.startsWith('field:')) {
      const fieldName = columnKey.slice(6);
      const candidateRecord = candidate as Record<string, unknown>;
      return formatDynamicColumnValue(candidateRecord[fieldName]);
    }

    return '';
  }

  function getTokenCheckboxState(
    tags: string[],
    groups: TokenGroups | null
  ): TokenCheckboxState {
    if (!groups) {
      return {
        includePartName: false,
        includePartNameTokens: false,
        includeCategoryTokens: false,
        includeParameterTokens: false,
        includeManufacturerPartTokens: false,
        includeSemanticTokens: false
      };
    }

    const activeTokenKeys = new Set(
      dedupTokens(tags)
        .map((token) => normalizeTokenKey(token))
        .filter(Boolean)
    );
    const hasAnyActiveToken = (tokens: string[]) =>
      tokens.some((token) => activeTokenKeys.has(normalizeTokenKey(token)));

    return {
      includePartName: hasAnyActiveToken(groups.nameValues),
      includePartNameTokens: hasAnyActiveToken(groups.nameTokens),
      includeCategoryTokens: hasAnyActiveToken(groups.categoryTokens),
      includeParameterTokens: hasAnyActiveToken(groups.parameterTokens),
      includeManufacturerPartTokens: hasAnyActiveToken(
        groups.manufacturerPartTokens
      ),
      includeSemanticTokens: hasAnyActiveToken(groups.semanticTokens)
    };
  }

  function applyTokenCheckboxState(state: TokenCheckboxState) {
    setIncludePartName(state.includePartName);
    setIncludePartNameTokens(state.includePartNameTokens);
    setIncludeCategoryTokens(state.includeCategoryTokens);
    setIncludeParameterTokens(state.includeParameterTokens);
    setIncludeManufacturerPartTokens(state.includeManufacturerPartTokens);
    setIncludeSemanticTokens(state.includeSemanticTokens);
  }

  function updateQueryTagsWithSync(
    nextTags: string[],
    groups: TokenGroups | null = tokenGroups
  ) {
    const deduped = dedupTokens(nextTags);
    setQueryTags(deduped);
    applyTokenCheckboxState(getTokenCheckboxState(deduped, groups));
  }

  async function fetchRateStatus(supplierPk?: string) {
    if (!serverContext.rate_status_url) {
      return;
    }

    const selectedSupplier = String(supplierPk ?? supplier ?? '').trim();
    const supplierValue = Number(selectedSupplier);

    if (
      selectedSupplier !== '' &&
      (!Number.isFinite(supplierValue) || supplierValue <= 0)
    ) {
      setRateStatus(null);
      setRateStatuses([]);
      return;
    }

    setLoadingRateStatus(true);

    try {
      const query =
        selectedSupplier === ''
          ? ''
          : `?supplier=${encodeURIComponent(selectedSupplier)}`;
      const response = await context.api.get(
        `${serverContext.rate_status_url}${query}`
      );
      const data = response?.data || {};
      const statuses: SupplierRateStatus[] = Array.isArray(data.suppliers)
        ? data.suppliers
        : [];

      setRateStatuses(statuses);

      if (selectedSupplier === '') {
        setRateStatus(null);
      } else {
        setRateStatus(statuses[0] || null);
      }
    } catch (error: any) {
      setRateStatus(null);
      setRateStatuses([]);
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

  useEffect(() => {
    if (!modalId || hasExpandedModal || candidates.length === 0) {
      return;
    }

    modals.updateModal({
      modalId,
      size: '90%'
    });
    setHasExpandedModal(true);
  }, [modalId, hasExpandedModal, candidates.length]);

  useEffect(() => {
    if (showTokens && !tokenDebugFetched && tokenDebugUrl) {
      fetchTokenDebug();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showTokens]);

  async function fetchTokenDebug() {
    setLoadingTokens(true);
    try {
      if (!tokenDebugUrl) {
        throw new Error('Token debug endpoint unavailable in plugin context');
      }

      const response = await context.api.get(
        `${tokenDebugUrl}?pk=${serverContext.part_pk}`
      );
      const data = response?.data || {};
      const sources: TokenSourceEntry[] = data.debug?.token_sources || [];
      const queryDebug = data.debug?.query_debug || {};
      const semanticHints: Record<string, string> =
        data.debug?.semantic_hints || {};
      const sourceByToken: Record<string, TokenPillSource> = {};

      const nameVals: string[] = [];
      const nameToks: string[] = [];
      const catToks: string[] = [];
      const paramToks: string[] = [];
      const mfgToks: string[] = [];
      const semanticToks: string[] = [];

      const querySourceTokenMap = queryDebug.source_token_map || {};
      for (const [sourceName, sourceTokens] of Object.entries(
        querySourceTokenMap
      )) {
        const mappedSource = QUERY_SOURCE_TO_PILL_SOURCE[sourceName];
        if (!mappedSource || !Array.isArray(sourceTokens)) {
          continue;
        }

        for (const token of sourceTokens) {
          setTokenSource(sourceByToken, String(token || ''), mappedSource);
        }
      }

      for (const src of sources) {
        const mappedSource = QUERY_SOURCE_TO_PILL_SOURCE[src.source];

        if (src.source === 'name' || src.source === 'description') {
          if (src.value?.trim()) {
            nameVals.push(src.value.trim());
            setTokenSource(sourceByToken, src.value.trim(), 'part-name');
          }
          for (const t of src.tokens || []) {
            if (t.trim()) {
              nameToks.push(t);
              setTokenSource(sourceByToken, t, 'name-token');
            }
          }
        } else if (src.source === 'category') {
          for (const t of src.tokens || []) {
            if (t.trim()) {
              catToks.push(t);
              setTokenSource(sourceByToken, t, 'category');
            }
          }
        } else if (src.source === 'parameter') {
          for (const t of src.tokens || []) {
            if (t.trim()) {
              paramToks.push(t);
              setTokenSource(sourceByToken, t, 'parameter');
            }
          }
        } else if (src.source === 'manufacturer_part') {
          for (const t of src.tokens || []) {
            if (t.trim()) {
              mfgToks.push(t);
              setTokenSource(sourceByToken, t, 'manufacturer-part');
            }
          }
        } else if (mappedSource) {
          for (const t of src.tokens || []) {
            if (t.trim()) {
              setTokenSource(sourceByToken, t, mappedSource);
            }
          }
        }
      }

      for (const value of Object.values(semanticHints)) {
        const v = String(value || '').trim();
        if (v) {
          semanticToks.push(v);
          setTokenSource(sourceByToken, v, 'semantic');
        }
      }

      const fallbackNameTokens = deriveNameTokensFromValues(nameVals);
      for (const token of fallbackNameTokens) {
        setTokenSource(sourceByToken, token, 'name-token');
      }
      const nameValueKeys = new Set(
        nameVals.map((value) => normalizeTokenKey(value)).filter(Boolean)
      );
      const filteredNameTokens = dedupTokens([
        ...nameToks,
        ...fallbackNameTokens
      ]).filter((token) => !nameValueKeys.has(normalizeTokenKey(token)));

      const otherGroupTokenKeys = new Set(
        [
          ...nameVals,
          ...filteredNameTokens,
          ...catToks,
          ...paramToks,
          ...mfgToks
        ].map((t) => normalizeTokenKey(t))
      );
      const uniqueSemanticToks = dedupTokens(semanticToks).filter(
        (t) => !otherGroupTokenKeys.has(normalizeTokenKey(t))
      );

      const groups: TokenGroups = {
        nameValues: nameVals,
        nameTokens: filteredNameTokens,
        categoryTokens: dedupTokens(catToks),
        parameterTokens: dedupTokens(paramToks),
        manufacturerPartTokens: dedupTokens(mfgToks),
        semanticTokens: uniqueSemanticToks
      };
      setTokenGroups(groups);
      setTagSourceByToken(sourceByToken);

      const finalTokens: string[] = queryDebug.final_query_tokens || [];
      const initialQueryTokens =
        finalTokens.length > 0
          ? dedupTokens(finalTokens)
          : dedupTokens(queryTags);
      applyTokenCheckboxState(
        getTokenCheckboxState(initialQueryTokens, groups)
      );

      if (finalTokens.length > 0) {
        // Keep initial pills aligned with checkbox-based behavior by deduping.
        setQueryTags(initialQueryTokens);
      }
    } catch (error: any) {
      setIsError(true);
      setStatusMessage(
        error?.response?.data?.message ||
          error?.message ||
          'Could not load query token metadata. Check plugin backend sync/restart.'
      );
    } finally {
      setTokenDebugFetched(true);
      setLoadingTokens(false);
    }
  }

  function dedupTokens(tokens: string[]): string[] {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const t of tokens) {
      const key = t.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        result.push(t);
      }
    }
    return result;
  }

  function toggleTokenGroup(groupTokens: string[], checked: boolean) {
    setQueryTags((prev) => {
      if (checked) {
        const seen = new Set(prev.map((t) => t.toLowerCase()));
        const next = [...prev];
        for (const t of groupTokens) {
          if (t.trim() && !seen.has(t.toLowerCase())) {
            seen.add(t.toLowerCase());
            next.push(t);
          }
        }
        return next;
      }
      const groupSet = new Set(groupTokens.map((t) => t.toLowerCase()));
      return prev.filter((t) => !groupSet.has(t.toLowerCase()));
    });
  }

  function renderRateBadge() {
    if (allSuppliersSelected) {
      if (activeRateStatuses.length === 0) {
        return (
          <Badge variant='light' color='gray'>
            API status unavailable
          </Badge>
        );
      }

      return (
        <Stack gap={4}>
          {activeRateStatuses.map((status) => {
            const supplierName =
              status.supplier_name || status.supplier_key || 'Supplier';
            const dailyLimit = Number(status.daily_limit || 0);
            const dailyCount = Number(status.daily_count || 0);
            const dailyRemaining =
              status.daily_remaining == null
                ? null
                : Number(status.daily_remaining);

            let color: 'green' | 'yellow' | 'red' | 'blue' = 'blue';
            if (dailyLimit > 0) {
              const ratio = dailyCount / Math.max(1, dailyLimit);
              if (dailyRemaining === 0) {
                color = 'red';
              } else if (ratio >= 0.9) {
                color = 'yellow';
              } else {
                color = 'green';
              }
            }

            const detailText =
              dailyLimit > 0
                ? `${dailyCount}/${dailyLimit} (${dailyRemaining} left)`
                : `${dailyCount} (unlimited)`;

            return (
              <Group key={String(status.supplier_pk)} gap='xs' align='center'>
                <Text size='xs' c='dimmed' style={{ minWidth: 110 }}>
                  {supplierName}
                </Text>
                <Badge variant='light' color={color} size='sm'>
                  {detailText}
                </Badge>
                <Badge variant='dot' color='blue' size='sm'>
                  {`${status.rate_limit_per_second || 0}/sec`}
                </Badge>
              </Group>
            );
          })}
        </Stack>
      );
    }

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

  function renderCompactRateBadge() {
    if (allSuppliersSelected) {
      if (activeRateStatuses.length === 0) {
        return (
          <Badge variant='light' color='gray' size='sm'>
            No status
          </Badge>
        );
      }

      const aggregateDailyLimit = activeRateStatuses.reduce(
        (total, status) => total + Math.max(Number(status.daily_limit || 0), 0),
        0
      );
      const aggregateDailyCount = activeRateStatuses.reduce(
        (total, status) => total + Math.max(Number(status.daily_count || 0), 0),
        0
      );

      const aggregateText =
        aggregateDailyLimit > 0
          ? `${aggregateDailyCount}/${aggregateDailyLimit}`
          : `${aggregateDailyCount} calls`;

      return (
        <Badge variant='light' color='blue' size='sm'>
          {aggregateText}
        </Badge>
      );
    }

    if (!rateStatus) {
      return (
        <Badge variant='light' color='gray' size='sm'>
          No status
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
      dailyLimit > 0 ? `${dailyCount}/${dailyLimit}` : `${dailyCount} calls`;

    return (
      <Badge variant='light' color={badgeColor} size='sm'>
        {dailyText}
      </Badge>
    );
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
        query: queryTags.join(' ').trim(),
        top_n: serverContext.top_n ?? 10,
        ...(supplier && { supplier: Number(supplier) }),
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

    const groupedCandidates = new Map<number, Candidate[]>();
    const selectedSupplierPk = Number(supplier);

    for (const candidate of selectedCandidates) {
      const candidateSupplierPk = Number(
        candidate._supplier_pk ?? selectedSupplierPk
      );

      if (!Number.isFinite(candidateSupplierPk) || candidateSupplierPk <= 0) {
        continue;
      }

      const existing = groupedCandidates.get(candidateSupplierPk) || [];
      existing.push(candidate);
      groupedCandidates.set(candidateSupplierPk, existing);
    }

    if (groupedCandidates.size === 0) {
      setIsError(true);
      setStatusMessage(
        supplier
          ? 'Selected candidates do not match the chosen supplier'
          : 'Selected candidates are missing supplier information'
      );
      return;
    }

    setApplying(true);

    try {
      let totalCreated = 0;
      let totalUpdated = 0;
      let totalErrors = 0;
      const supplierErrors: string[] = [];

      for (const [supplierPk, candidatesForSupplier] of groupedCandidates) {
        const payload = {
          pk: serverContext.part_pk,
          supplier: supplierPk,
          candidates: candidatesForSupplier
        };

        try {
          const response = await context.api.post(
            serverContext.apply_url,
            payload
          );
          const data = response?.data || {};

          if (data.message !== 'OK') {
            totalErrors += candidatesForSupplier.length;
            supplierErrors.push(
              `Supplier ${supplierPk}: ${data.message || 'Apply candidates failed'}`
            );
            continue;
          }

          totalCreated += Number(data.created || 0);
          totalUpdated += Number(data.updated || 0);
          totalErrors += Number(data.errors || 0);
        } catch (error: any) {
          totalErrors += candidatesForSupplier.length;
          supplierErrors.push(
            `Supplier ${supplierPk}: ${
              error?.response?.data?.message ||
              error?.message ||
              'Apply candidates failed'
            }`
          );
        }
      }

      const summary = `Applied candidates: created=${totalCreated}, updated=${totalUpdated}, errors=${totalErrors}`;
      setIsError(totalErrors > 0);
      setStatusMessage(summary);

      notifications.show({
        title: 'Supplier Scout',
        message:
          supplierErrors.length > 0
            ? `${summary}. ${supplierErrors.join(' | ')}`
            : summary,
        color: totalErrors > 0 ? 'yellow' : 'green'
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

  function setColumnVisibility(column: ResultColumnKey, visible: boolean) {
    setVisibleColumns((previous) => ({
      ...previous,
      [column]: visible
    }));
  }

  return (
    <Stack gap='xs'>
      <Text c='dimmed' size='sm'>
        Search supplier matches, select candidates, then create or update
        supplier parts.
      </Text>

      {statusMessage && (
        <Alert color={isError ? 'red' : 'green'}>{statusMessage}</Alert>
      )}

      <NativeSelect
        label='Supplier'
        size='xs'
        data={supplierOptions}
        value={supplier}
        onChange={(event) => setSupplier(event.currentTarget.value)}
      />

      <Paper withBorder p='xs' radius='md'>
        <UnstyledButton
          onClick={() => setShowApiUsage(!showApiUsage)}
          style={{ width: '100%' }}
        >
          <Group justify='space-between' align='center'>
            <Group gap='xs'>
              <Text size='xs' c='dimmed'>
                {showApiUsage ? '▼' : '▶'}
              </Text>
              <Text size='xs' fw={600}>
                API Usage
              </Text>
            </Group>
            {loadingRateStatus ? (
              <Loader size='xs' />
            ) : (
              renderCompactRateBadge()
            )}
          </Group>
        </UnstyledButton>
        <Collapse expanded={showApiUsage}>
          <Stack gap='xs' mt='xs'>
            {renderRateBadge()}
            <Group justify='flex-end'>
              <Button
                variant='subtle'
                size='xs'
                onClick={() => fetchRateStatus()}
                loading={loadingRateStatus}
              >
                Refresh
              </Button>
            </Group>
          </Stack>
        </Collapse>
      </Paper>

      <Paper withBorder p='xs' radius='md'>
        <UnstyledButton
          onClick={() => setShowTokens(!showTokens)}
          style={{ width: '100%' }}
        >
          <Group gap='xs'>
            <Text size='xs' c='dimmed'>
              {showTokens ? '▼' : '▶'}
            </Text>
            <Text size='xs' fw={600}>
              Search Query
            </Text>
          </Group>
        </UnstyledButton>
        <Collapse expanded={showTokens}>
          <Stack gap='sm' mt='xs'>
            {loadingTokens && (
              <Group gap='xs'>
                <Loader size='xs' />
                <Text size='xs' c='dimmed'>
                  Loading token groups…
                </Text>
              </Group>
            )}
            {tokenGroups && (
              <Stack gap='xs'>
                <Text size='xs' c='dimmed'>
                  Select which token groups to include:
                </Text>
                <Group gap='md'>
                  <Checkbox
                    label='Part name'
                    checked={includePartName}
                    disabled={tokenGroups.nameValues.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludePartName(checked);
                      toggleTokenGroup(tokenGroups.nameValues, checked);
                    }}
                  />
                  <Checkbox
                    label='Part name tokens'
                    checked={includePartNameTokens}
                    disabled={tokenGroups.nameTokens.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludePartNameTokens(checked);
                      toggleTokenGroup(tokenGroups.nameTokens, checked);
                    }}
                  />
                  <Checkbox
                    label='Category names'
                    checked={includeCategoryTokens}
                    disabled={tokenGroups.categoryTokens.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludeCategoryTokens(checked);
                      toggleTokenGroup(tokenGroups.categoryTokens, checked);
                    }}
                  />
                  <Checkbox
                    label='Parameters'
                    checked={includeParameterTokens}
                    disabled={tokenGroups.parameterTokens.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludeParameterTokens(checked);
                      toggleTokenGroup(tokenGroups.parameterTokens, checked);
                    }}
                  />
                  <Checkbox
                    label='Manufacturer part'
                    checked={includeManufacturerPartTokens}
                    disabled={tokenGroups.manufacturerPartTokens.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludeManufacturerPartTokens(checked);
                      toggleTokenGroup(
                        tokenGroups.manufacturerPartTokens,
                        checked
                      );
                    }}
                  />
                  <Checkbox
                    label='Semantic hints'
                    checked={includeSemanticTokens}
                    disabled={tokenGroups.semanticTokens.length === 0}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked;
                      setIncludeSemanticTokens(checked);
                      toggleTokenGroup(tokenGroups.semanticTokens, checked);
                    }}
                  />
                </Group>
              </Stack>
            )}
            <TagsInput
              label='Search query tags'
              description='Each tag is sent as a search keyword. Add or remove tags manually.'
              value={queryTags}
              onChange={(nextTags) => updateQueryTagsWithSync(nextTags)}
              disabled={loadingTokens}
              renderPill={({ value, onRemove, disabled, reorderProps }) => {
                const pillValue = String(value || '');
                const source = getPillSourceForTag(pillValue, tagSourceByToken);
                const sourceMeta = TOKEN_PILL_META[source];

                return (
                  <Pill
                    withRemoveButton={!disabled}
                    onRemove={onRemove}
                    style={{
                      backgroundColor: `var(--mantine-color-${sourceMeta.color}-light)`,
                      color: `var(--mantine-color-${sourceMeta.color}-8)`,
                      border: `1px solid var(--mantine-color-${sourceMeta.color}-3)`
                    }}
                    {...reorderProps}
                  >
                    {pillValue}
                  </Pill>
                );
              }}
              placeholder={
                queryTags.length === 0 ? 'Type and press Enter to add tags' : ''
              }
              splitChars={[' ', ',']}
              clearable
            />
            {queryTags.length > 0 && (
              <Stack gap={4}>
                <Text size='xs' c='dimmed'>
                  Token source colours:
                </Text>
                <Group gap='xs'>
                  {activeTokenPillSources.map((source) => (
                    <Badge
                      key={source}
                      size='sm'
                      variant='light'
                      color={TOKEN_PILL_META[source].color}
                    >
                      {TOKEN_PILL_META[source].label}
                    </Badge>
                  ))}
                </Group>
              </Stack>
            )}
          </Stack>
        </Collapse>
      </Paper>

      <Group gap='xs' align='center' wrap='wrap'>
        <Group gap={6} align='center'>
          <Text size='xs' c='dimmed' fw={600}>
            Search Quantity
          </Text>
          <Tooltip
            multiline
            w={300}
            label='Optional quantity overrides for supplier price-break selection. Leave blank to use plugin defaults shown in each field.'
          >
            <Badge size='xs' variant='outline' color='gray'>
              ?
            </Badge>
          </Tooltip>
        </Group>
        <TextInput
          label='Min Qty'
          size='xs'
          value={minQty}
          onChange={(event) => setMinQty(event.currentTarget.value)}
          placeholder={minQtyPlaceholder}
          type='number'
          style={{ width: 210 }}
        />
        <TextInput
          label='Max Qty'
          size='xs'
          value={maxQty}
          onChange={(event) => setMaxQty(event.currentTarget.value)}
          placeholder={maxQtyPlaceholder}
          type='number'
          style={{ width: 210 }}
        />
      </Group>

      {candidates.length > 0 && (
        <Paper withBorder p='xs' radius='md'>
          <Stack gap='xs'>
            <Group gap='md' align='center' wrap='wrap'>
              <Text size='xs' c='dimmed' fw={600}>
                Columns
              </Text>
              <Checkbox
                size='xs'
                label='Supplier'
                checked={visibleColumns.supplier}
                onChange={(event) =>
                  setColumnVisibility('supplier', event.currentTarget.checked)
                }
              />
              <Checkbox
                size='xs'
                label='SKU'
                checked={visibleColumns.sku}
                onChange={(event) =>
                  setColumnVisibility('sku', event.currentTarget.checked)
                }
              />
              <Checkbox
                size='xs'
                label='MPN'
                checked={visibleColumns.mpn}
                onChange={(event) =>
                  setColumnVisibility('mpn', event.currentTarget.checked)
                }
              />
              <Checkbox
                size='xs'
                label='Description'
                checked={visibleColumns.description}
                onChange={(event) =>
                  setColumnVisibility(
                    'description',
                    event.currentTarget.checked
                  )
                }
              />
              <Checkbox
                size='xs'
                label='Available'
                checked={visibleColumns.available}
                onChange={(event) =>
                  setColumnVisibility('available', event.currentTarget.checked)
                }
              />
              <Checkbox
                size='xs'
                label='Unit Price'
                checked={visibleColumns.unitPrice}
                onChange={(event) =>
                  setColumnVisibility('unitPrice', event.currentTarget.checked)
                }
              />
              {serverContext.show_score === true && (
                <Checkbox
                  size='xs'
                  label='Score'
                  checked={visibleColumns.score}
                  onChange={(event) =>
                    setColumnVisibility('score', event.currentTarget.checked)
                  }
                />
              )}
              <MultiSelect
                label='Additional Attributes'
                size='xs'
                placeholder='Choose extra columns'
                data={availableDynamicColumns}
                value={selectedDynamicColumns}
                onChange={setSelectedDynamicColumns}
                searchable
                clearable
                maxValues={5}
                style={{ minWidth: 280, maxWidth: 420 }}
              />
            </Group>

            <Text size='xs' c='dimmed'>
              Hidden columns are still included when applying selected
              candidates.
            </Text>

            <ScrollArea>
              <Table striped withTableBorder highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Select</Table.Th>
                    <Table.Th>Status</Table.Th>
                    {visibleColumns.supplier && <Table.Th>Supplier</Table.Th>}
                    {visibleColumns.sku && <Table.Th>SKU</Table.Th>}
                    {visibleColumns.mpn && <Table.Th>MPN</Table.Th>}
                    {visibleColumns.description && (
                      <Table.Th>Description</Table.Th>
                    )}
                    {visibleColumns.available && <Table.Th>Available</Table.Th>}
                    {visibleColumns.unitPrice && (
                      <Table.Th>Unit Price</Table.Th>
                    )}
                    {selectedDynamicColumns.map((columnKey) => (
                      <Table.Th key={columnKey}>
                        {dynamicColumnLabelByKey[columnKey] || columnKey}
                      </Table.Th>
                    ))}
                    {serverContext.show_score === true &&
                      visibleColumns.score && <Table.Th>Score</Table.Th>}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {candidates.map((candidate) => {
                    const sku = String(candidate.supplier_part_number || '');
                    const selected = selectedSkus.has(sku);
                    const isExisting =
                      candidate.existing_supplier_part === true;
                    const supplierName =
                      candidate._supplier_name ||
                      suppliers.find(
                        (item) => item.pk === candidate._supplier_pk
                      )?.name ||
                      suppliers.find((item) => item.pk === Number(supplier))
                        ?.name ||
                      '';

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
                        {visibleColumns.supplier && (
                          <Table.Td>{supplierName}</Table.Td>
                        )}
                        {visibleColumns.sku && (
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
                        )}
                        {visibleColumns.mpn && (
                          <Table.Td>
                            {candidate.manufacturer_part_number || ''}
                          </Table.Td>
                        )}
                        {visibleColumns.description && (
                          <Table.Td>{candidate.description || ''}</Table.Td>
                        )}
                        {visibleColumns.available && (
                          <Table.Td>
                            {candidate.available_quantity ?? ''}
                          </Table.Td>
                        )}
                        {visibleColumns.unitPrice && (
                          <Table.Td>
                            {formatUnitPrice(candidate.unit_price)}
                          </Table.Td>
                        )}
                        {selectedDynamicColumns.map((columnKey) => (
                          <Table.Td key={`${sku}-${columnKey}`}>
                            {getDynamicColumnCellValue(candidate, columnKey)}
                          </Table.Td>
                        ))}
                        {serverContext.show_score === true &&
                          visibleColumns.score && (
                            <Table.Td>{candidate.score ?? ''}</Table.Td>
                          )}
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Stack>
        </Paper>
      )}

      <Group justify='flex-end'>
        {onClose && (
          <Button variant='default' onClick={onClose}>
            Cancel
          </Button>
        )}
        <Button onClick={searchMatches} loading={searching}>
          Find Matches
        </Button>
        {candidates.length > 0 && (
          <Button
            onClick={applySelection}
            loading={applying}
            disabled={selectedCandidates.length === 0 || applying}
          >
            Add / Update Selected
          </Button>
        )}
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
  const modalId = `supplierscout-part-match-${Date.now()}`;

  modals.open({
    modalId,
    title: serverContext?.title || 'Supplier Part Matching',
    size: '45%',
    styles: {
      content: {
        transition: 'max-width 240ms ease'
      }
    },
    children: (
      <LocalizedComponent locale={inventreeContext.locale}>
        <SupplierScoutMatcher
          context={inventreeContext}
          serverContext={serverContext}
          modalId={modalId}
          onClose={() => modals.closeAll()}
        />
      </LocalizedComponent>
    )
  });
}
