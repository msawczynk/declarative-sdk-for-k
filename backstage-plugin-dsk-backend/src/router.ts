import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

import { LoggerService } from '@backstage/backend-plugin-api';
import { Config } from '@backstage/config';
import express from 'express';
import Router from 'express-promise-router';

export type RouterOptions = {
  config: Config;
  logger: LoggerService;
};

type PlanProcessResult = {
  exitCode: number;
  stdout: string;
  stderr: string;
};

const execFileAsync = promisify(execFile);
const planExitCodes = new Set([0, 2, 4]);

export async function createRouter(options: RouterOptions): Promise<express.Router> {
  const { config, logger } = options;
  const router = Router();

  router.use(express.json());

  router.get('/health', (_request, response) => {
    response.json({ status: 'ok' });
  });

  router.get('/plan', async (request, response) => {
    const manifestPath = queryString(request.query.manifestPath)
      ?? config.getOptionalString('dsk.manifestPath');

    if (!manifestPath) {
      response.status(400).json({
        error: 'Missing DSK manifest path',
        nextAction: 'Set dsk.manifestPath in app-config.yaml or pass manifestPath as a query parameter',
      });
      return;
    }

    const binaryPath = config.getOptionalString('dsk.binaryPath') ?? 'dsk';
    const timeoutMs = config.getOptionalNumber('dsk.timeoutMs') ?? 30000;
    const maxBufferBytes = config.getOptionalNumber('dsk.maxBufferBytes') ?? 1024 * 1024;
    const result = await runPlan(binaryPath, manifestPath, timeoutMs, maxBufferBytes);

    if (!planExitCodes.has(result.exitCode)) {
      logger.warn(`dsk plan failed with exit code ${result.exitCode}: ${result.stderr}`);
      response.status(502).json({
        error: 'dsk plan failed',
        exitCode: result.exitCode,
        stderr: result.stderr,
      });
      return;
    }

    if (result.stderr) {
      logger.debug(`dsk plan stderr: ${result.stderr}`);
    }

    try {
      response.json({
        ...JSON.parse(result.stdout),
        exitCode: result.exitCode,
      });
    } catch (error) {
      logger.warn(`dsk plan emitted invalid JSON: ${String(error)}`);
      response.status(502).json({
        error: 'dsk plan emitted invalid JSON',
        exitCode: result.exitCode,
      });
    }
  });

  return router;
}

function queryString(value: unknown): string | undefined {
  if (typeof value === 'string' && value.length > 0) {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === 'string' && value[0].length > 0) {
    return value[0];
  }
  return undefined;
}

async function runPlan(
  binaryPath: string,
  manifestPath: string,
  timeoutMs: number,
  maxBufferBytes: number,
): Promise<PlanProcessResult> {
  try {
    const { stdout, stderr } = await execFileAsync(
      binaryPath,
      ['plan', manifestPath, '--json'],
      {
        timeout: timeoutMs,
        maxBuffer: maxBufferBytes,
      },
    );
    return { exitCode: 0, stdout: String(stdout), stderr: String(stderr) };
  } catch (error) {
    const processError = error as {
      code?: number | string;
      stdout?: string | Buffer;
      stderr?: string | Buffer;
    };
    if (typeof processError.code === 'number') {
      return {
        exitCode: processError.code,
        stdout: String(processError.stdout ?? ''),
        stderr: String(processError.stderr ?? ''),
      };
    }
    throw error;
  }
}
