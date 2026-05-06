#!/usr/bin/env python3
"""
Data migration script to retroactively find correlations for existing open incidents.

This script queries all open/investigating/resolved incidents and finds
correlations based on the dependency map. It creates incident_correlation
records for any incidents found on upstream dependency components.

Usage:
    cd backend
    python scripts/backfill_correlations.py
"""

import asyncio
import sys
sys.path.insert(0, '/home/akbar-ali/DEVOPS/projects/ims/backend')

import ulid
import structlog
from sqlalchemy import select
from db.mysql import AsyncSessionLocal
from models import WorkItem, ComponentType, WorkItemStatus, IncidentCorrelation
from core.correlation import _get_upstream_dependencies

log = structlog.get_logger()


async def backfill_correlations():
    """Find and create correlations for all existing open incidents."""
    async with AsyncSessionLocal() as session:
        # Fetch all non-closed incidents
        result = await session.execute(
            select(WorkItem).where(
                WorkItem.status.in_([
                    WorkItemStatus.OPEN,
                    WorkItemStatus.INVESTIGATING,
                    WorkItemStatus.RESOLVED,
                ])
            )
        )
        all_incidents = result.scalars().all()
        
        log.info("backfill_started", total_incidents=len(all_incidents))
        
        correlations_created = 0
        
        # For each incident, check if it should be cascaded from upstream dependencies
        for incident in all_incidents:
            upstream_dependencies = _get_upstream_dependencies(incident.component_type.value)
            
            if not upstream_dependencies:
                continue
            
            # Check for each upstream dependency
            for upstream_component in upstream_dependencies:
                upstream_result = await session.execute(
                    select(WorkItem).where(
                        (WorkItem.component_type == ComponentType(upstream_component))
                        & (WorkItem.status.in_([
                            WorkItemStatus.OPEN,
                            WorkItemStatus.INVESTIGATING,
                            WorkItemStatus.RESOLVED,
                        ]))
                    )
                )
                upstream_incidents = upstream_result.scalars().all()
                
                for upstream_incident in upstream_incidents:
                    # Check if correlation already exists
                    existing = await session.execute(
                        select(IncidentCorrelation).where(
                            (IncidentCorrelation.root_incident_id == upstream_incident.id)
                            & (IncidentCorrelation.cascaded_incident_id == incident.id)
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue
                    
                    # Create correlation
                    correlation = IncidentCorrelation(
                        id=str(ulid.new()),
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident.id,
                        correlation_reason=f"{upstream_component} failure detected before this {incident.component_type.value} incident",
                    )
                    session.add(correlation)
                    correlations_created += 1
                    
                    log.info(
                        "correlation_created",
                        root_incident_id=upstream_incident.id,
                        cascaded_incident_id=incident.id,
                        root_component=upstream_component,
                    )
        
        await session.commit()
        log.info("backfill_completed", correlations_created=correlations_created)
        return correlations_created


if __name__ == "__main__":
    count = asyncio.run(backfill_correlations())
    print(f"✓ Created {count} correlation records")
