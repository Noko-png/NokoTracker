import { ChevronDown, ChevronUp, Plus, X } from "lucide-react";
import type { TrainingPlan } from "./api/client";

const maxTrainingPlans = 31;

export function TrainingSeriesPlans({ plans, value, repeating, required, onChange }: {
  plans: Pick<TrainingPlan, "id" | "name">[];
  value: string[];
  repeating: boolean;
  required: boolean;
  onChange: (value: string[]) => void;
}) {
  const slots = value.length ? value : [""];

  function movePlan(index: number, offset: number) {
    const reordered = [...slots];
    const [plan] = reordered.splice(index, 1);
    reordered.splice(index + offset, 0, plan);
    onChange(reordered);
  }

  return (
    <fieldset className="calendar-training-plans">
      <legend>{repeating ? "Trainingspläne in Reihenfolge" : "Verknüpfter Trainingsplan"}</legend>
      {slots.map((planId, index) => (
        <div className="calendar-training-plan-row" key={index}>
          <label>
            <span>{repeating || slots.length > 1 ? `Trainingsplan ${index + 1}` : "Trainingsplan"}</span>
            <select
              value={planId}
              required={required || slots.length > 1}
              onChange={(event) => onChange(slots.map((id, position) => position === index ? event.target.value : id))}
            >
              <option value="">{required || slots.length > 1 ? "Trainingsplan wählen" : "Ohne Trainingsplan"}</option>
              {plans.map((plan) => <option value={plan.id} key={plan.id}>{plan.name}</option>)}
            </select>
          </label>
          {slots.length > 1 && (
            <div className="calendar-training-plan-actions">
              <button className="icon-button" type="button" aria-label={`Plan ${index + 1} nach oben verschieben`} disabled={index === 0} onClick={() => movePlan(index, -1)}>
                <ChevronUp size={16} />
              </button>
              <button className="icon-button" type="button" aria-label={`Plan ${index + 1} nach unten verschieben`} disabled={index === slots.length - 1} onClick={() => movePlan(index, 1)}>
                <ChevronDown size={16} />
              </button>
              <button className="icon-button" type="button" aria-label={`Plan ${index + 1} entfernen`} onClick={() => onChange(slots.filter((_, position) => position !== index))}>
                <X size={16} />
              </button>
            </div>
          )}
        </div>
      ))}
      {repeating && plans.length > 0 && slots.length < maxTrainingPlans && (
        <button className="button secondary" type="button" disabled={slots.some((id) => !id)} onClick={() => onChange([...slots, ""])}>
          <Plus size={16} />Plan hinzufügen
        </button>
      )}
      {!plans.length && <small>Lege einen Trainingsplan unter Stammdaten → Training an.</small>}
      {repeating && slots.length > 1 && <small>Nach dem letzten Plan beginnt die Reihenfolge von vorn. Pausentage ändern die Reihenfolge nicht.</small>}
    </fieldset>
  );
}
