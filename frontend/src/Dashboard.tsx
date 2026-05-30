// Import for type checking
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
import { useEffect, useMemo, useState } from 'react';

type SupplierMetricsContext = {
  metrics_url?: string;
};

type SupplierDashboardMetrics = {
  supplier_pk: number;
  supplier_key: string;
  supplier_name: string;
  configured: boolean;
  query_metrics?: {
    total_queries?: number;
    ok_queries?: number;
    error_queries?: number;
    total_candidates_returned?: number;
  };
  api_usage?: {
    rate_limit_per_second?: number;
    daily_limit?: number;
    daily_count?: number;
    daily_remaining?: number | null;
  };
  cache_status?: {
    enabled?: boolean;
    cache_backend?: string;
    cache_ttl_seconds?: number;
    cache_file_count?: number;
    cache_size_bytes?: number;
  };
};

/**
 * Render a custom dashboard item with the provided context
 * Refer to the InvenTree documentation for the context interface
 * https://docs.inventree.org/en/stable/extend/plugins/ui/#plugin-context
 */
function SupplierScoutDashboardItem({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const serverContext = useMemo(() => {
    return (context.context || {}) as SupplierMetricsContext;
  }, [context.context]);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [suppliers, setSuppliers] = useState<SupplierDashboardMetrics[]>([]);

  async function loadMetrics() {
    if (!serverContext.metrics_url) {
      setError('Missing dashboard metrics URL in plugin context');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await context.api.get(serverContext.metrics_url);
      const data = response?.data || {};
      setSuppliers(data.suppliers || []);
    } catch (fetchError: any) {
      setError(
        fetchError?.response?.data?.message ||
          fetchError?.message ||
          'Failed to load supplier metrics'
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverContext.metrics_url]);

  function formatCache(cacheStatus: SupplierDashboardMetrics['cache_status']) {
    if (!cacheStatus || cacheStatus.enabled !== true) {
      return 'Disabled';
    }

    const ttl = Number(cacheStatus.cache_ttl_seconds || 0);
    const files = Number(cacheStatus.cache_file_count || 0);
    return `${files} files / TTL ${ttl}s`;
  }

  return (
    <Paper withBorder p='md' radius='md'>
      <Stack gap='sm'>
        <Group justify='space-between'>
          <Title order={5}>Supplier Scout Query Metrics</Title>
          <Button
            size='xs'
            variant='light'
            onClick={loadMetrics}
            loading={loading}
          >
            Refresh
          </Button>
        </Group>

        {error && <Alert color='red'>{error}</Alert>}

        {suppliers.length === 0 ? (
          <Text c='dimmed' size='sm'>
            No supplier metrics available.
          </Text>
        ) : (
          <ScrollArea>
            <Table withTableBorder striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Supplier</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Queries (ok/error)</Table.Th>
                  <Table.Th>Candidates</Table.Th>
                  <Table.Th>API Budget</Table.Th>
                  <Table.Th>Cache</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {suppliers.map((supplier) => {
                  const query = supplier.query_metrics || {};
                  const usage = supplier.api_usage || {};
                  const configured = supplier.configured === true;

                  return (
                    <Table.Tr
                      key={`${supplier.supplier_key}-${supplier.supplier_pk}`}
                    >
                      <Table.Td>{supplier.supplier_name}</Table.Td>
                      <Table.Td>
                        <Badge
                          color={configured ? 'green' : 'gray'}
                          variant='light'
                        >
                          {configured ? 'Configured' : 'Missing credentials'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {(query.total_queries || 0) +
                          ` (${query.ok_queries || 0}/${query.error_queries || 0})`}
                      </Table.Td>
                      <Table.Td>
                        {query.total_candidates_returned || 0}
                      </Table.Td>
                      <Table.Td>
                        {(usage.daily_count || 0) +
                          '/' +
                          (usage.daily_limit || 0) +
                          ` day, ${usage.rate_limit_per_second || 0}/sec`}
                      </Table.Td>
                      <Table.Td>{formatCache(supplier.cache_status)}</Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Stack>
    </Paper>
  );
}

// This is the function which is called by InvenTree to render the actual dashboard
//  component
export function renderSupplierScoutDashboardItem(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <SupplierScoutDashboardItem context={context} />;
}
