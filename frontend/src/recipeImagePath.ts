const recipeImageDataUrl = /^data:image\/[a-z0-9][a-z0-9.+-]*;base64,[a-z0-9+/]+={0,2}$/i;

export function localRecipeImagePath(path?: string | null): string | undefined {
  if (!path || !recipeImageDataUrl.test(path)) return undefined;
  const payloadLength = path.length - path.indexOf(",") - 1;
  return payloadLength % 4 === 0 ? path : undefined;
}

export function recipeImageUpdate(path: string): string | null | undefined {
  // Preserve an existing reference on unrelated edits. Removing it sends null.
  return path === "" ? null : localRecipeImagePath(path);
}
