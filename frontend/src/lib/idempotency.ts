export type LogicalOperationKeys = {
  get(action: string): string;
  complete(action: string): void;
};

export function createLogicalOperationKeys(
  scope: string,
  createUuid: () => string = () => crypto.randomUUID(),
): LogicalOperationKeys {
  const keys = new Map<string, string>();
  return {
    get(action) {
      const existing = keys.get(action);
      if (existing) return existing;
      const created = `${scope}-${action}-${createUuid()}`;
      keys.set(action, created);
      return created;
    },
    complete(action) {
      keys.delete(action);
    },
  };
}
