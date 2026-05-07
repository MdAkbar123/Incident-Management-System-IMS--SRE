# backend/core/correlation.py

import ulid
import structlog
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from db.mysql import AsyncSessionLocal
from db.redis import get_redis
from models import WorkItem, ComponentType, WorkItemStatus, IncidentCorrelation


log = structlog.get_logger()


# Static dependency map: if A is in the list, then A depends on the key
DEPENDENCY_MAP: dict[str, list[str]] = {
    "RDBMS":       ["API", "CACHE", "ASYNC_QUEUE", "NOSQL", "MCP_HOST"],
    "MCP_HOST":    ["API"],
    "API":         [],
    "CACHE":       [],
    "ASYNC_QUEUE": [],
    "NOSQL":       [],
}


def _get_upstream_dependencies(component_type: str) -> list[str]:
    """
    Return all components that the given component type depends on.
    
    Example: _get_upstream_dependencies("CACHE") -> ["RDBMS"]
    because CACHE is in DEPENDENCY_MAP["RDBMS"]'s value.
    """
    upstream = []
    for dependency_root, dependents in DEPENDENCY_MAP.items():
        if component_type in dependents:
            upstream.append(dependency_root)
    return upstream


async def detect_and_store_correlations(
    incident_id: str,
    component_type: str,
    component_id: str,
) -> int:
    """
    Detect correlation for a newly created incident.
    
    When a new incident is created on component_type, check if there are
    any open incidents on the upstream dependencies. If found, store
    the relationship in incident_correlations table.
    
    Returns: count of correlations created.
    """
    redis = get_redis()
    upstream_dependencies = _get_upstream_dependencies(component_type)
    
    if not upstream_dependencies:
        log.debug(
            "no_upstream_dependencies",
            incident_id=incident_id,
            component_type=component_type,
        )
        return 0
    
    correlations_created = 0
    
    try:
        async with AsyncSessionLocal() as session:
            # Query for any open incidents on upstream dependency components
            for upstream_component in upstream_dependencies:
                result = await session.execute(
                    select(WorkItem).where(
                        (WorkItem.component_type == ComponentType(upstream_component))
                        & (WorkItem.status.in_([
                            WorkItemStatus.OPEN,
                            WorkItemStatus.INVESTIGATING,
                            WorkItemStatus.RESOLVED,
                        ]))
                    )
                )
                upstream_incidents = result.scalars().all()
                
                for upstream_incident in upstream_incidents:
                    # Create a correlation record linking root → cascaded
                    correlation = IncidentCorrelation(
                        id=str(ulid.new()),
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident_id,
                        correlation_reason=f"{upstream_component} failure detected before this {component_type} incident",
                    )
                    session.add(correlation)
                    correlations_created += 1
                    
                    log.info(
                        "correlation_detected",
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident_id,
                        root_component=upstream_component,
                        cascaded_component=component_type,
                    )
            
            await session.commit()

    
    except SQLAlchemyError as e:
        log.error(
            "correlation_detection_error",
            incident_id=incident_id,
            error=str(e),
        )
        return 0
    
    return correlations_created
# core/correlation.py — add this new function

def _get_downstream_dependents(component_type: str) -> list[str]:
    """
    Return all components that depend ON the given component type.
    
    Example: _get_downstream_dependents("RDBMS") -> ["API", "CACHE", "ASYNC_QUEUE", "NOSQL", "MCP_HOST"]
    because those are the values listed under DEPENDENCY_MAP["RDBMS"].
    """
    return DEPENDENCY_MAP.get(component_type, [])


async def detect_downstream_correlations(
    incident_id: str,
    component_type: str,
) -> int:
    """
    When a ROOT incident is created, find any already-open downstream incidents
    and create correlation rows pointing back to this one as the root.
    
    This is the reverse of detect_and_store_correlations — it runs when
    a potential root cause incident is created, to catch downstream incidents
    that already exist (e.g. created milliseconds earlier in a cascade).
    """
    downstream_dependents = _get_downstream_dependents(component_type)

    if not downstream_dependents:
        return 0

    correlations_created = 0

    try:
        async with AsyncSessionLocal() as session:
            for downstream_component in downstream_dependents:
                result = await session.execute(
                    select(WorkItem).where(
                        (WorkItem.component_type == ComponentType(downstream_component))
                        & (WorkItem.status.in_([
                            WorkItemStatus.OPEN,
                            WorkItemStatus.INVESTIGATING,
                            WorkItemStatus.RESOLVED,
                        ]))
                    )
                )
                downstream_incidents = result.scalars().all()

                for downstream_incident in downstream_incidents:
                    # Avoid duplicates
                    existing = await session.execute(
                        select(IncidentCorrelation).where(
                            (IncidentCorrelation.root_incident_id == incident_id)
                            & (IncidentCorrelation.cascaded_incident_id == downstream_incident.id)
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue

                    correlation = IncidentCorrelation(
                        id=str(ulid.new()),
                        root_incident_id=incident_id,
                        cascaded_incident_id=downstream_incident.id,
                        correlation_reason=f"{component_type} failure detected before this {downstream_component} incident",
                    )
                    session.add(correlation)
                    correlations_created += 1

                    log.info(
                        "downstream_correlation_detected",
                        root_incident_id=incident_id,
                        cascaded_incident_id=downstream_incident.id,
                        root_component=component_type,
                        cascaded_component=downstream_component,
                    )

            await session.commit()

    except SQLAlchemyError as e:
        log.error("downstream_correlation_error", incident_id=incident_id, error=str(e))
        return 0

    return correlations_created