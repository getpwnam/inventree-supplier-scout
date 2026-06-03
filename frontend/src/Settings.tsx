import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert, List, Stack, Text } from '@mantine/core';
import { LocalizedComponent } from './locale';

function PluginSettingsDisplay({
  context: _context
}: {
  context: InvenTreePluginContext;
}) {
  return (
    <Alert color='blue' title='Supplier Scout'>
      <Stack gap='xs'>
        <Text size='sm'>
          Configure supplier IDs, credentials, and query defaults from the
          plugin settings below, then use Supplier Scout from each part record
          to find supplier matches.
        </Text>
        <List size='sm' spacing='xs'>
          <List.Item>
            Add the supplier company ID and API credentials for each enabled
            supplier integration.
          </List.Item>
          <List.Item>
            Review default quantity overrides to control price-break lookups.
          </List.Item>
          <List.Item>
            Use the dashboard widget to monitor API usage and cache health.
          </List.Item>
        </List>
      </Stack>
    </Alert>
  );
}

export function renderPluginSettings(context: InvenTreePluginContext) {
  return (
    <LocalizedComponent locale={context.locale}>
      <PluginSettingsDisplay context={context} />
    </LocalizedComponent>
  );
}
