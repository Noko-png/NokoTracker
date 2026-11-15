// Only administrators may fall back to another available profile.
export function resolveProfileId(
  users: { id: number }[],
  storedId: number,
  access: { is_admin: boolean; user_id: number | null },
): number | null {
  if (!access.is_admin) {
    return users.some((user) => user.id === access.user_id) ? access.user_id : null;
  }
  return users.find((user) => user.id === storedId)?.id ?? users[0]?.id ?? null;
}
