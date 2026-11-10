from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload
from pydantic import ValidationError

from .. import crud, models, schemas
from ..database import get_db
from ..services.calendar_schedule import ensure_occurrence, ensure_training_event


plans_router = APIRouter(prefix="/training/plans", tags=["training"])
sessions_router = APIRouter(prefix="/training/sessions", tags=["training"])
exercises_router = APIRouter(prefix="/training/exercises", tags=["training"])


def ensure_user_exists(db: Session, user_id: int | None) -> None:
    if user_id is not None and crud.get(db, models.User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")


def get_plan_or_404(db: Session, plan_id: int) -> models.TrainingPlan:
    plan = crud.get(db, models.TrainingPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Training plan not found")
    return plan


def get_exercise_or_404(db: Session, exercise_id: int) -> models.TrainingExercise:
    exercise = crud.get(db, models.TrainingExercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Training exercise not found")
    return exercise


def get_session_or_404(db: Session, session_id: int) -> models.TrainingSession:
    training_session = crud.get(db, models.TrainingSession, session_id)
    if training_session is None:
        raise HTTPException(status_code=404, detail="Training session not found")
    return training_session


def validate_session_sets(
    db: Session,
    plan_id: int,
    sets: list[schemas.TrainingSessionSetCreate],
) -> None:
    if not sets:
        raise HTTPException(status_code=422, detail="Training session needs at least one set")

    exercise_ids = {set_in.exercise_id for set_in in sets}
    valid_exercise_ids = {
        exercise_id
        for (exercise_id,) in db.query(models.TrainingExercise.id)
        .filter(models.TrainingExercise.plan_id == plan_id)
        .filter(models.TrainingExercise.id.in_(exercise_ids))
        .all()
    }
    invalid_ids = sorted(exercise_ids - valid_exercise_ids)
    if invalid_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Exercises do not belong to this plan: {', '.join(map(str, invalid_ids))}",
        )


def validate_calendar_link(db: Session, data: schemas.TrainingSessionBase, session_id: int | None = None):
    if data.calendar_event_id is None:
        if data.calendar_occurrence_start_at is not None:
            raise HTTPException(422, "Zum Kalenderzeitpunkt fehlt der Kalendertermin.")
        return
    if data.calendar_occurrence_start_at is None:
        raise HTTPException(422, "Bitte den Kalenderzeitpunkt des Trainings angeben.")
    event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == data.calendar_event_id).first()
    if event is None:
        raise HTTPException(404, "Kalendertermin nicht gefunden.")
    plan = ensure_training_event(db, event)
    if plan.id != data.plan_id:
        raise HTTPException(422, "Das Training muss den verknuepften Trainingsplan verwenden.")
    principal = db.info.get("principal")
    user_id = data.user_id if data.user_id is not None else (principal.user_id if principal and not principal.is_admin else None)
    if user_id != event.user_id or user_id != plan.user_id:
        raise HTTPException(422, "Training und Kalendertermin muessen zum gleichen Profil gehoeren.")
    target = ensure_occurrence(event, data.calendar_occurrence_start_at)
    query = db.query(models.TrainingSession).filter(
        models.TrainingSession.calendar_event_id == event.id,
        models.TrainingSession.calendar_occurrence_start_at == target,
    )
    if session_id is not None:
        query = query.filter(models.TrainingSession.id != session_id)
    if query.first():
        raise HTTPException(409, "Dieses Training wurde bereits protokolliert.")
    data.calendar_occurrence_start_at = target


@plans_router.get("", response_model=list[schemas.TrainingPlanRead])
def list_training_plans(
    user_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(models.TrainingPlan).options(selectinload(models.TrainingPlan.exercises))
    if user_id is not None:
        query = query.filter(models.TrainingPlan.user_id == user_id)
    return (
        query.order_by(models.TrainingPlan.name, models.TrainingPlan.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@plans_router.post("", response_model=schemas.TrainingPlanRead, status_code=status.HTTP_201_CREATED)
def create_training_plan(
    plan_in: schemas.TrainingPlanCreate,
    db: Session = Depends(get_db),
):
    ensure_user_exists(db, plan_in.user_id)
    plan = models.TrainingPlan(**plan_in.model_dump(exclude={"exercises"}))
    db.add(plan)
    db.flush()
    for index, exercise_in in enumerate(plan_in.exercises):
        exercise_data = exercise_in.model_dump()
        exercise_data["position"] = exercise_data.get("position") or index
        plan.exercises.append(models.TrainingExercise(**exercise_data))
    db.commit()
    db.refresh(plan)
    return plan


@plans_router.patch("/{plan_id}", response_model=schemas.TrainingPlanRead)
def update_training_plan(
    plan_id: int,
    plan_in: schemas.TrainingPlanUpdate,
    db: Session = Depends(get_db),
):
    plan = get_plan_or_404(db, plan_id)
    ensure_user_exists(db, plan_in.user_id)
    return crud.update(db, plan, plan_in)


@plans_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = get_plan_or_404(db, plan_id)
    crud.delete(db, plan)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@plans_router.post(
    "/{plan_id}/exercises",
    response_model=schemas.TrainingExerciseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_training_exercise(
    plan_id: int,
    exercise_in: schemas.TrainingExerciseCreate,
    db: Session = Depends(get_db),
):
    plan = get_plan_or_404(db, plan_id)
    exercise = models.TrainingExercise(plan_id=plan.id, **exercise_in.model_dump())
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


@exercises_router.patch("/{exercise_id}", response_model=schemas.TrainingExerciseRead)
def update_training_exercise(
    exercise_id: int,
    exercise_in: schemas.TrainingExerciseUpdate,
    db: Session = Depends(get_db),
):
    exercise = get_exercise_or_404(db, exercise_id)
    return crud.update(db, exercise, exercise_in)


@exercises_router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_exercise(exercise_id: int, db: Session = Depends(get_db)):
    exercise = get_exercise_or_404(db, exercise_id)
    crud.delete(db, exercise)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@sessions_router.get("", response_model=list[schemas.TrainingSessionRead])
def list_training_sessions(
    user_id: int | None = None,
    plan_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(models.TrainingSession).options(
        selectinload(models.TrainingSession.plan),
        selectinload(models.TrainingSession.sets).selectinload(models.TrainingSessionSet.exercise),
    )
    if user_id is not None:
        query = query.filter(models.TrainingSession.user_id == user_id)
    if plan_id is not None:
        query = query.filter(models.TrainingSession.plan_id == plan_id)
    return (
        query.order_by(models.TrainingSession.trained_at.desc(), models.TrainingSession.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@sessions_router.post(
    "",
    response_model=schemas.TrainingSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_training_session(
    session_in: schemas.TrainingSessionCreate,
    db: Session = Depends(get_db),
):
    get_plan_or_404(db, session_in.plan_id)
    ensure_user_exists(db, session_in.user_id)
    validate_session_sets(db, session_in.plan_id, session_in.sets)
    validate_calendar_link(db, session_in)

    training_session = models.TrainingSession(
        **session_in.model_dump(exclude={"sets"})
    )
    db.add(training_session)
    db.flush()
    for index, set_in in enumerate(session_in.sets, start=1):
        set_data = set_in.model_dump()
        set_data["set_index"] = set_data.get("set_index") or index
        training_session.sets.append(models.TrainingSessionSet(**set_data))
    db.commit()
    db.refresh(training_session)
    return training_session


@sessions_router.patch("/{session_id}", response_model=schemas.TrainingSessionRead)
def update_training_session(
    session_id: int,
    session_in: schemas.TrainingSessionUpdate,
    db: Session = Depends(get_db),
):
    training_session = get_session_or_404(db, session_id)
    merged_data = {name: getattr(training_session, name) for name in schemas.TrainingSessionBase.model_fields}
    merged_data.update(session_in.model_dump(exclude_unset=True, exclude={"sets"}))
    if "calendar_event_id" in session_in.model_fields_set and session_in.calendar_event_id is None:
        merged_data["calendar_occurrence_start_at"] = None
    try:
        merged = schemas.TrainingSessionBase.model_validate(merged_data)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    plan_id = merged.plan_id
    get_plan_or_404(db, plan_id)
    ensure_user_exists(db, merged.user_id)
    validate_calendar_link(db, merged, training_session.id)

    # Validate all input before modifying persistent rows; invalid sets must not
    # leak a partially changed session into a caller's next transaction.
    if session_in.sets is not None:
        validate_session_sets(db, plan_id, session_in.sets)
    elif plan_id != training_session.plan_id:
        existing_sets = [schemas.TrainingSessionSetCreate.model_validate(row, from_attributes=True) for row in training_session.sets]
        validate_session_sets(db, plan_id, existing_sets)

    update_data = session_in.model_dump(exclude_unset=True, exclude={"sets"})
    if "calendar_event_id" in update_data or "calendar_occurrence_start_at" in update_data:
        update_data["calendar_occurrence_start_at"] = merged.calendar_occurrence_start_at
    for field, value in update_data.items():
        setattr(training_session, field, value)

    if session_in.sets is not None:
        training_session.sets.clear()
        db.flush()
        for index, set_in in enumerate(session_in.sets, start=1):
            set_data = set_in.model_dump()
            set_data["set_index"] = set_data.get("set_index") or index
            training_session.sets.append(models.TrainingSessionSet(**set_data))

    db.add(training_session)
    db.commit()
    db.refresh(training_session)
    return training_session


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_session(session_id: int, db: Session = Depends(get_db)):
    training_session = get_session_or_404(db, session_id)
    crud.delete(db, training_session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@exercises_router.get(
    "/{exercise_id}/results",
    response_model=list[schemas.TrainingExerciseResultRead],
)
def list_training_exercise_results(
    exercise_id: int,
    sort: str = Query("date-desc", pattern="^(date-desc|weight-desc|reps-desc|volume-desc)$"),
    user_id: int | None = None,
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    exercise = get_exercise_or_404(db, exercise_id)
    query = (
        db.query(models.TrainingSessionSet)
        .join(models.TrainingSession)
        .join(models.TrainingPlan)
        .options(
            selectinload(models.TrainingSessionSet.session).selectinload(models.TrainingSession.plan),
            selectinload(models.TrainingSessionSet.exercise),
        )
        .filter(models.TrainingSessionSet.exercise_id == exercise.id)
    )
    if user_id is not None:
        query = query.filter(models.TrainingSession.user_id == user_id)

    results = [
        {
            "set_id": set_row.id,
            "session_id": set_row.session_id,
            "plan_id": set_row.session.plan_id,
            "plan_name": set_row.session.plan.name,
            "trained_at": set_row.session.trained_at,
            "exercise_id": set_row.exercise_id,
            "exercise_name": set_row.exercise.name,
            "set_index": set_row.set_index,
            "weight_kg": set_row.weight_kg,
            "reps": set_row.reps,
            "volume": round(set_row.weight_kg * set_row.reps, 2),
            "notes": set_row.notes,
        }
        for set_row in query.all()
    ]

    sorters = {
        "date-desc": lambda item: (item["trained_at"], item["session_id"], item["set_index"]),
        "weight-desc": lambda item: (item["weight_kg"], item["reps"], item["trained_at"]),
        "reps-desc": lambda item: (item["reps"], item["weight_kg"], item["trained_at"]),
        "volume-desc": lambda item: (item["volume"], item["weight_kg"], item["trained_at"]),
    }
    return sorted(results, key=sorters[sort], reverse=True)[:limit]
