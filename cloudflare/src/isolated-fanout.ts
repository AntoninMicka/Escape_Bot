export type FanoutResult = PromiseSettledResult<void>;

export async function isolatedFanout<T>(
  targets: readonly T[],
  deliver: (target: T) => Promise<unknown>,
  timeoutMs = 2_000,
): Promise<FanoutResult[]> {
  const boundedTimeout = Math.max(1, Math.min(30_000, Math.round(timeoutMs)));
  return Promise.allSettled(targets.map(async (target) => {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([
        deliver(target),
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => reject(new Error("fanout_timeout")), boundedTimeout);
        }),
      ]);
    } finally {
      if (timeout !== undefined) clearTimeout(timeout);
    }
  }));
}
