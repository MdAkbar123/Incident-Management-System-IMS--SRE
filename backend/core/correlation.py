"""
Incident Correlation Engine
=============================
Detects relationships between incidents using multiple detection methods:
  - Dependency Graph: Component dependencies (hardcoded)
  - Temporal: Incidents within 30 seconds of each other
  - Semantic: Similar error codes/patterns
"""
import structlog
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from db.mysql import AsyncSessionLocal
from models import WorkItem, IncidentRelationship, RelationshipType, ComponentType
from sqlalchemy import select
import ulid

log = structlog.get_logger()

# ── Dependency Graph ─────────────────────────────────────
# Component dependencies: if A fails, B typically fails next
# Format: ComponentType -> [dependent ComponentTypes]
COMPONENT_DEPENDENCIES = {
    ComponentType.RDBMS: [
        ComponentType.API,
        ComponentType.CACHE,
        ComponentType.ASYNC_QUEUE,
    ],
    ComponentType.CACHE: [
        ComponentType.API,
        ComponentType.ASYNC_QUEUE,
    ],
    ComponentType.ASYNC_QUEUE: [
        ComponentType.CACHE,
    ],
    ComponentType.MCP_HOST: [
        ComponentType.API,
    ],
}


async def detect_dependency_relationships(
    new_work_item: WorkItem,
    existing_work_items: List[WorkItem],
    time_window_seconds: int = 30,
) -> List[Tuple[WorkItem, float, str]]:
    """
    Detect incidents caused by component dependencies.
    
    Returns list of (related_work_item, confidence, reason) tuples.
    """
    related = []
    
    # Get dependencies that would cause this component to fail
    causing_components = set()
    for component_type, dependents in COMPONENT_DEPENDENCIES.items():
        if new_work_item.component_type in dependents:
            causing_components.add(component_type)
    
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(seconds=time_window_seconds)
    
    for existing in existing_work_items:
        if existing.id == new_work_item.id:
            continue
        
        # Check if this component could have caused the new one
        if existing.component_type in causing_components:
            # Higher confidence if closer in time
            time_diff = (new_work_item.created_at - existing.created_at).total_seconds()
            if 0 < time_diff < time_window_seconds:
                # Confidence decreases with time: 1.0 at 0s, 0.6 at 30s
                confidence = max(0.6, 1.0 - (time_diff / (time_window_seconds * 2)))
                
                reason = (
                    f"{existing.component_type.value} failure ({time_diff:.1f}s earlier) "
                    f"typically cascades to {new_work_item.component_type.value}"
                )
                related.append((existing, confidence, reason))
    
    return related


async def detect_temporal_relationships(
    new_work_item: WorkItem,
    existing_work_items: List[WorkItem],
    time_window_seconds: int = 30,
) -> List[Tuple[WorkItem, float, str]]:
    """
    Detect incidents occurring in close temporal proximity.
    
    Returns list of (related_work_item, confidence, reason) tuples.
    """
    related = []
    
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(seconds=time_window_seconds)
    
    for existing in existing_work_items:
        if existing.id == new_work_item.id:
            continue
        
        # Check if incidents are close in time
        time_diff = abs((new_work_item.created_at - existing.created_at).total_seconds())
        if 0 < time_diff < time_window_seconds:
            # Higher confidence for closer timing
            confidence = max(0.5, 1.0 - (time_diff / time_window_seconds))
            
            reason = (
                f"Temporal correlation: {existing.component_type.value} incident "
                f"{time_diff:.1f}s before {new_work_item.component_type.value} incident"
            )
            related.append((existing, confidence, reason))
    
    return related


async def detect_semantic_relationships(
    new_work_item: WorkItem,
    existing_work_items: List[WorkItem],
) -> List[Tuple[WorkItem, float, str]]:
    """
    Detect incidents with similar error patterns.
    
    This is a placeholder for pattern-matching logic that could be enhanced.
    Returns list of (related_work_item, confidence, reason) tuples.
    """
    related = []
    
    # For now, same component type in recent history = semantic relation
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    for existing in existing_work_items:
        if existing.id == new_work_item.id:
            continue
        
        if (existing.component_type == new_work_item.component_type and
            existing.created_at > cutoff_time):
            
            reason = (
                f"Semantic pattern: Repeated {existing.component_type.value} failures "
                f"suggest systemic issue (check config or resource limits)"
            )
            confidence = 0.7  # Moderate confidence for pattern match
            related.append((existing, confidence, reason))
    
    return related


async def find_related_incidents(
    work_item_id: str,
    time_window_seconds: int = 30,
) -> Tuple[List[IncidentRelationship], List[IncidentRelationship]]:
    """
    Find all incidents that could be related to the given work item.
    
    Returns (root_cause_incidents, cascaded_incidents).
    """
    async with AsyncSessionLocal() as session:
        # Get the target work item
        result = await session.execute(
            select(WorkItem).where(WorkItem.id == work_item_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            return [], []
        
        # Get all recent incidents (could be related)
        cutoff = target.created_at - timedelta(seconds=time_window_seconds * 2)
        result = await session.execute(
            select(WorkItem)
            .where(WorkItem.created_at >= cutoff)
            .order_by(WorkItem.created_at.desc())
        )
        all_incidents = result.scalars().all()
        
        # Run all detection methods
        dep_related = await detect_dependency_relationships(
            target, all_incidents, time_window_seconds
        )
        temp_related = await detect_temporal_relationships(
            target, all_incidents, time_window_seconds
        )
        sem_related = await detect_semantic_relationships(target, all_incidents)
        
        # Deduplicate and merge results
        seen = set()
        relationships = []
        
        for related_item, confidence, reason in dep_related + temp_related + sem_related:
            if related_item.id not in seen:
                seen.add(related_item.id)
                
                # Determine if this is a root cause or cascade
                # If related incident happened before, it's a root cause
                is_root_cause = related_item.created_at < target.created_at
                
                rel_type = (
                    RelationshipType.ROOT_CAUSE if is_root_cause
                    else RelationshipType.CASCADED_FROM
                )
                
                # Determine detection method (use the first one found)
                if any(r[0].id == related_item.id for r in dep_related):
                    method = "dependency_graph"
                elif any(r[0].id == related_item.id for r in temp_related):
                    method = "temporal"
                else:
                    method = "semantic"
                
                rel = IncidentRelationship(
                    id=str(ulid.new()),
                    source_incident_id=related_item.id if is_root_cause else target.id,
                    target_incident_id=target.id if is_root_cause else related_item.id,
                    relationship_type=rel_type,
                    confidence=confidence,
                    detection_method=method,
                    reason=reason,
                )
                relationships.append(rel)
        
        # Separate into root causes and cascades
        root_causes = [r for r in relationships if r.relationship_type == RelationshipType.ROOT_CAUSE]
        cascades = [r for r in relationships if r.relationship_type == RelationshipType.CASCADED_FROM]
        
        return root_causes, cascades


async def save_relationships(relationships: List[IncidentRelationship]) -> None:
    """Save detected relationships to database."""
    if not relationships:
        return
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for rel in relationships:
                session.add(rel)
        
        log.info(
            "relationships_saved",
            count=len(relationships),
        )
