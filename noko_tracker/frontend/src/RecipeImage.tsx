import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { localRecipeImagePath } from "./recipeImagePath";

export function RecipeImage({ path, alt, className }: {
  path?: string | null;
  alt: string;
  className?: string;
}) {
  if (!path) return null;

  const source = localRecipeImagePath(path);
  if (!source) {
    return <small className="recipe-image-unavailable">Gespeicherter Bildverweis blockiert.</small>;
  }

  const image = <img alt={alt} src={source} />;
  return className ? <div className={className}>{image}</div> : image;
}

export function RecipeImageField({ path, onChange }: {
  path: string;
  onChange: (path: string) => void;
}) {
  const pendingReader = useRef<FileReader | null>(null);
  const [error, setError] = useState("");

  useEffect(() => () => pendingReader.current?.abort(), []);

  function readImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;

    pendingReader.current?.abort();
    setError("");
    const reader = new FileReader();
    pendingReader.current = reader;
    reader.onload = () => {
      pendingReader.current = null;
      const source = typeof reader.result === "string" ? localRecipeImagePath(reader.result) : undefined;
      if (source) {
        onChange(source);
      } else {
        setError("Bitte eine lokale Bilddatei auswählen.");
      }
    };
    reader.onerror = () => {
      pendingReader.current = null;
      setError("Die Bilddatei konnte nicht gelesen werden.");
    };
    reader.readAsDataURL(file);
  }

  function removeImage() {
    pendingReader.current?.abort();
    pendingReader.current = null;
    setError("");
    onChange("");
  }

  return (
    <div className="recipe-builder-field">
      <label className="recipe-builder-field">
        <span>Bilddatei</span>
        <input accept="image/*" onChange={readImage} type="file" />
      </label>
      {error && <small role="alert">{error}</small>}
      <div className="recipe-image-preview">
        {path ? (
          <>
            <RecipeImage alt="Rezeptbild Vorschau" path={path} />
            <button className="button secondary" onClick={removeImage} type="button">
              Bild entfernen
            </button>
          </>
        ) : (
          <span>Keine Bildvorschau</span>
        )}
      </div>
    </div>
  );
}
