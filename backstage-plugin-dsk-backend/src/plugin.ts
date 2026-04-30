import { coreServices, createBackendPlugin } from '@backstage/backend-plugin-api';

import { createRouter as createDskRouter } from './router';

export { createRouter } from './router';

export const dskPlugin = createBackendPlugin({
  pluginId: 'dsk',
  register(env) {
    env.registerInit({
      deps: {
        config: coreServices.rootConfig,
        httpRouter: coreServices.httpRouter,
        logger: coreServices.logger,
      },
      async init({ config, httpRouter, logger }) {
        httpRouter.use(await createDskRouter({ config, logger }));
      },
    });
  },
});

export default dskPlugin;
