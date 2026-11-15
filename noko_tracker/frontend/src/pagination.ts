export async function loadAllPages<T>(
  fetchPage: (skip: number, limit: number) => Promise<T[]>,
  pageSize = 500,
): Promise<T[]> {
  const items: T[] = [];
  for (let skip = 0; ; skip += pageSize) {
    const page = await fetchPage(skip, pageSize);
    items.push(...page);
    if (page.length < pageSize) return items;
  }
}
