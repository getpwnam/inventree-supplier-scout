// Import for type checking
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { notifications } from '@mantine/notifications';

/**
 * Custom spotlight action with the provided context
 * Refer to the InvenTree documentation for the context interface
 * https://docs.inventree.org/en/stable/extend/plugins/ui/#plugin-context
 */
export function SupplierScoutSpotlightAction(context: InvenTreePluginContext) {
  const username = context.user?.username?.();

  notifications.show({
    title: 'Supplier Scout',
    message: username
      ? `Hi ${username}. Open a part record and use Supplier Part Matching to search supplier offers.`
      : 'Open a part record and use Supplier Part Matching to search supplier offers.',
    color: 'blue',
    autoClose: 6000
  });
}
